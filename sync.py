"""
Ana senkronizasyon mantigi.

Akis:
  1. Spotify playlist'lerini listele
  2. Her playlist icin snapshot_id kontrol et - degismemisse atla (zaman kazandirir)
  3. Sarkilari cek, DB'de zaten eklenmis olanlari atla
  4. Yeni sarkilari YouTube Music'te ara + eslestir
  5. Skor yuksekse ekle, dusukse "supheli" olarak isaretle
  6. Snapshot'i guncelle

Kullanim:
  python sync.py                  -> tum playlist'leri senkronize et
  python sync.py --list           -> sadece playlist'leri listele
  python sync.py --playlist <id>  -> tek playlist
"""
import sys
import json
import argparse

# Windows konsolu Turkce/Yunanca karakterlerde cokmesin diye ciktiyi UTF-8 yap
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import config
import db
import spotify_client as spc
import ytmusic_client as ytc
import matcher
import telegram_notify


def sync_playlist(sp, yt, sp_playlist, force=False, dry_run=False, sync_deletes=True,
                  do_import=False):
    pid = sp_playlist["id"]
    name = sp_playlist["name"]

    # Snapshot kontrolu - degismemisse atla (import ve dry_run'da atlamayiz)
    current_snap = sp_playlist.get("snapshot_id") or spc.get_playlist_snapshot(sp, pid)
    last_snap = db.get_snapshot(pid)
    if not force and not dry_run and not do_import and last_snap == current_snap:
        print(f"[ATLA] '{name}' degismemis.")
        return

    mode = "[ILK DOLUM] " if do_import else ("[KURU CALISMA] " if dry_run else "")
    print(f"\n{mode}[SENKRON] '{name}' ({sp_playlist.get('track_count', '?')} sarki)")

    # Spotify listesinin SU ANKI hali
    tracks = spc.get_tracks(sp, pid)
    current_ids = {t["id"] for t in tracks}

    # Spotify listesinin ONCEKI hali (DB'de kayitli)
    previous_ids = db.get_track_state(pid)

    if do_import:
        # ILK DOLUM: tum sarkilari ekle (fark mantigini yoksay).
        # Zaten DB'de "synced" olanlari yine atlariz (mukerrer onleme).
        new_ids = current_ids
        removed_ids = set()
    elif previous_ids is None:
        # ILK KEZ goruluyor. Referans olarak kaydet, HICBIR SEY ekleme.
        print("  (Bu liste ilk kez goruluyor; mevcut hali referans olarak kaydedildi, "
              "ekleme yapilmadi. Tum sarkilari aktarmak icin --import kullan.)")
        if not dry_run:
            db.set_track_state(pid, current_ids)
            db.set_snapshot(pid, current_snap, pid)
        return
    else:
        # YENI eklenenler = simdiki - onceki
        new_ids = current_ids - previous_ids
        # CIKARILANLAR = onceki - simdiki (Spotify'dan silinenler)
        removed_ids = previous_ids - current_ids if sync_deletes else set()

    if not new_ids and not removed_ids:
        print("  (Degisiklik yok.)")
        if not dry_run:
            db.set_track_state(pid, current_ids)
            db.set_snapshot(pid, current_snap, pid)
        return

    if new_ids:
        print(f"  ({len(new_ids)} yeni sarki tespit edildi.)")
    if removed_ids:
        print(f"  ({len(removed_ids)} sarki Spotify'dan cikarilmis.)")

    # Hedef YT Music listesi
    if dry_run:
        yt_playlist_id, existed = _find_playlist(yt, name)
        if not existed:
            print("  (YouTube'da bu isimde liste YOK; canli modda olusturulurdu)")
            yt_playlist_id = None
    else:
        yt_playlist_id, existed = ytc.get_or_create_playlist(yt, name)

    # IMPORT modunda: YouTube'da ZATEN olan sarkilari oku, onlari atla.
    # Boylece ayni isimli mevcut listeye sadece EKSIK olanlar eklenir (mukerrer olmaz).
    existing_keys = set()
    if do_import and yt_playlist_id and existed:
        existing_keys = ytc.get_existing_track_keys(yt, yt_playlist_id)
        if existing_keys:
            print(f"  (YouTube listesinde zaten {len(existing_keys)} sarki var; "
                  f"bunlar atlanacak, sadece eksikler eklenecek.)")

    added = pending = skipped = 0
    new_tracks = [t for t in tracks if t["id"] in new_ids]

    for t in new_tracks:
        # IMPORT: YouTube'da isim+sanatci olarak zaten var mi? Varsa atla (arama yapmadan).
        if do_import and existing_keys:
            key = matcher.track_key(t["name"], t["artists"])
            if key and key in existing_keys:
                skipped += 1
                if not dry_run:
                    db.mark_synced(t["id"], yt_playlist_id, "", t["name"], t["artists"])
                continue

        if dry_run:
            added += 1
            print(f"  + (EKLENECEKTI) {t['artists']} - {t['name']}")
            continue

        # Bu program daha once eklemis mi? (ayni sarki baska listeden gelmis olabilir)
        if db.is_synced(t["id"], yt_playlist_id):
            continue

        candidates = ytc.search_song(yt, t["name"], t["artists"])
        best, score, scored = matcher.best_match(t, candidates)

        if best and score >= config.MIN_CONFIDENCE_SCORE and best.get("videoId"):
            ok, already = ytc.add_to_playlist(yt, yt_playlist_id, best["videoId"])
            if ok:
                db.mark_synced(t["id"], yt_playlist_id, best["videoId"],
                               t["name"], t["artists"])
                # import'ta ayni listede tekrar denk gelirse diye anahtara ekle
                if do_import:
                    k = matcher.track_key(t["name"], t["artists"])
                    if k:
                        existing_keys.add(k)
                added += 1
                tag = " (zaten vardi)" if already else ""
                print(f"  + {t['artists']} - {t['name']}  (skor {score}){tag}")
            else:
                _stash_pending(t, yt_playlist_id, scored)
                pending += 1
        else:
            _stash_pending(t, yt_playlist_id, scored)
            pending += 1
            print(f"  ? SUPHELI: {t['artists']} - {t['name']}  (en iyi skor {score})")

    # --- SILME: Spotify'dan cikarilan sarkilari YouTube'dan da sil ---
    # GUVENLIK: sadece BIZIM ekledigimiz (DB'de videoId'si kayitli) sarkilari sileriz.
    # Elle ekledigin sarkilara dokunmayiz.
    removed = 0
    if removed_ids and yt_playlist_id:
        our_tracks = db.get_synced_for_playlist(yt_playlist_id)
        # spotify_track_id -> kayit eslemesi
        our_by_sid = {r["spotify_track_id"]: r for r in our_tracks}
        for sid in removed_ids:
            rec = our_by_sid.get(sid)
            if not rec or not rec.get("yt_video_id"):
                continue  # biz eklememisiz ya da videoId yok -> dokunma
            if dry_run:
                removed += 1
                print(f"  - (SILINECEKTI) {rec['artist_name']} - {rec['track_name']}")
            else:
                ok = ytc.remove_from_playlist(yt, yt_playlist_id, rec["yt_video_id"])
                if ok:
                    db.remove_synced(sid, yt_playlist_id)
                    removed += 1
                    print(f"  - SILINDI: {rec['artist_name']} - {rec['track_name']}")

    # Durumu guncelle (dry_run'da DOKUNMAYIZ)
    if not dry_run:
        db.set_track_state(pid, current_ids)
        db.set_snapshot(pid, current_snap, yt_playlist_id)

    if dry_run:
        line = f"  -> [KURU] Eklenecek: {added}"
        if do_import and skipped:
            line += f" | Zaten var (atlanacak): {skipped}"
        if sync_deletes and not do_import:
            line += f" | Silinecek: {removed}"
        print(line)
        print(f"     (Hicbir sey YouTube'a yazilmadi, bu sadece onizleme.)")
    else:
        line = f"  -> Eklendi: {added} | Supheli: {pending}"
        if do_import and skipped:
            line += f" | Zaten vardi: {skipped}"
        if sync_deletes and not do_import:
            line += f" | Silindi: {removed}"
        print(line)

    # Telegram ozeti icin sonucu dondur (sadece gercek degisiklik olduysa anlamli)
    return {
        "name": name,
        "added": added,
        "removed": removed if (sync_deletes and not do_import) else 0,
        "pending": pending,
    }


def _find_playlist(yt, name):
    """Var olan playlist'i bul ama OLUSTURMA. Donen: (id_or_None, bulundu_mu)."""
    try:
        existing = yt.get_library_playlists(limit=100)
    except Exception:
        return None, False
    for pl in existing:
        if pl.get("title") == name:
            return pl["playlistId"], True
    return None, False


def _stash_pending(track, yt_playlist_id, scored):
    """Supheli sarkiyi adaylariyla birlikte incelemeye kaydet."""
    candidates = [
        {"title": c["title"], "artists": c["artists"],
         "duration_sec": c["duration_sec"], "videoId": c["videoId"],
         "is_music": c["is_music"], "score": s}
        for c, s in scored[:3]
    ]
    db.add_pending(
        track["id"], yt_playlist_id, track["name"], track["artists"],
        track["duration_sec"], json.dumps(candidates, ensure_ascii=False)
    )


WATCHLIST_FILE = "watchlist.txt"


def read_watchlist():
    """watchlist.txt'ten takip edilecek liste id'lerini oku."""
    import os
    if not os.path.exists(WATCHLIST_FILE):
        return []
    ids = []
    with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                ids.append(line)
    return ids


def add_to_watchlist(playlist_id):
    """Bir id'yi watchlist'e ekle (zaten varsa ekleme). Eklendiyse True doner."""
    ids = read_watchlist()
    if playlist_id in ids:
        return False
    with open(WATCHLIST_FILE, "a", encoding="utf-8") as f:
        f.write(playlist_id + "\n")
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", action="store_true", help="Playlist'leri listele")
    parser.add_argument("--playlist", help="Tek bir playlist id'si senkronize et")
    parser.add_argument("--all", action="store_true",
                        help="watchlist'i yoksay, TUM listeleri senkronize et")
    parser.add_argument("--force", action="store_true", help="Snapshot'i yoksay, hepsini tara")
    parser.add_argument("--dry-run", action="store_true",
                        help="Onizleme: hicbir sey eklemez/silmez, sadece ne yapacagini gosterir")
    parser.add_argument("--no-delete", action="store_true",
                        help="Silmeyi kapat: Spotify'dan cikarilanlar YouTube'da kalir")
    parser.add_argument("--import", dest="do_import", action="store_true",
                        help="Ilk dolum: listenin TUM sarkilarini YouTube'a aktar (sifirdan)")
    args = parser.parse_args()

    config.validate()
    db.init_db()

    sp = spc.get_client()
    playlists = spc.list_playlists(sp)

    if args.list:
        print("Playlist'lerin:")
        for pl in playlists:
            print(f"  {pl['id']}  {pl['name']}  ({pl['track_count']} sarki)")
        return

    yt = ytc.get_client()

    if args.playlist:
        # Tek liste
        target = next((p for p in playlists if p["id"] == args.playlist), None)
        if not target:
            print("Playlist bulunamadi.")
            return
        targets = [target]
    elif args.all:
        # Hepsi
        targets = playlists
    else:
        # Sadece watchlist'tekiler (varsayilan davranis)
        watch_ids = read_watchlist()
        if not watch_ids:
            print("watchlist.txt bos. Takip edilecek liste yok.")
            print("Liste id'lerini gormek icin: python sync.py --list")
            print("Sonra watchlist.txt'e eklemek istedigin id'leri yaz (her satira bir tane).")
            print("Ya da tum listeleri senkronlamak icin: python sync.py --all")
            return
        targets = [p for p in playlists if p["id"] in watch_ids]
        # watchlist'te olup Spotify'da bulunamayan id varsa uyar
        found_ids = {p["id"] for p in targets}
        for wid in watch_ids:
            if wid not in found_ids:
                print(f"  ! Uyari: watchlist'teki '{wid}' Spotify listelerinde bulunamadi.")
        print(f"Takip edilen {len(targets)} liste senkronlaniyor.")

    results = []
    for pl in targets:
        r = sync_playlist(sp, yt, pl, force=args.force, dry_run=args.dry_run,
                          sync_deletes=not args.no_delete, do_import=args.do_import)
        if r:
            results.append(r)

    if not args.dry_run:
        print("\nBitti. Supheli eslesmeleri gormek icin: python review.py")
        _send_telegram_summary(results)
    else:
        print("\n[KURU CALISMA] bitti. Hicbir sey eklenmedi.")


def _send_telegram_summary(results):
    """Her senkron sonunda Telegram'a ozet gonder (degisiklik olsa da olmasa da)."""
    changed = [r for r in results
               if r["added"] > 0 or r["removed"] > 0 or r["pending"] > 0]

    if not changed:
        # Degisiklik yok ama yine de "calistim" bildirimi gonder
        telegram_notify.send(
            "<b>🎵 Spotify → YouTube Music senkron</b>\n\n"
            f"Calisti. {len(results)} liste kontrol edildi, degisiklik yok."
        )
        return

    lines = ["<b>🎵 Spotify → YouTube Music senkron</b>", ""]
    toplam_eklendi = toplam_silindi = toplam_supheli = 0
    for r in changed:
        parts = []
        if r["added"]:
            parts.append(f"+{r['added']} eklendi")
            toplam_eklendi += r["added"]
        if r["removed"]:
            parts.append(f"−{r['removed']} silindi")
            toplam_silindi += r["removed"]
        if r["pending"]:
            parts.append(f"?{r['pending']} supheli")
            toplam_supheli += r["pending"]
        lines.append(f"• <b>{r['name']}</b>: " + ", ".join(parts))

    lines.append("")
    ozet = f"Toplam: +{toplam_eklendi}"
    if toplam_silindi:
        ozet += f" / −{toplam_silindi}"
    if toplam_supheli:
        ozet += f" / ?{toplam_supheli} supheli (review.py)"
    lines.append(ozet)

    telegram_notify.send("\n".join(lines))


if __name__ == "__main__":
    main()
