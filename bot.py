"""
Telegram buton botu - senkronizasyonu Telegram'dan butonlarla yonetir.

Surekli calisir. SADECE config.TELEGRAM_CHAT_ID'den gelenleri isler (guvenlik).

Hem metin komutlari (/sync, /list...) hem butonlar calisir.
Calistirmak icin:  python bot.py   (surekli acik kalmali)
"""
import ssl
import json
import time
import urllib.request
import urllib.parse
import certifi
from collections import defaultdict

import config
import db
import spotify_client as spc
import ytmusic_client as ytc
import matcher
import sync as sync_module

# SSL dogrulamasi ACIK (certifi CA paketi ile). Windows sistem deposu bu
# sunucuda bozuk kok yuzunden zinciri kuramiyordu; certifi cozuyor.
# URL'de bot token gidiyor, bu yuzden dogrulama guvenlik icin sart.
_CTX = ssl.create_default_context(cafile=certifi.where())

API = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}"

# Review oturumu icin basit durum (tek kullanici oldugu icin global yeter)
_review_state = {"queue": [], "index": 0}


def _api(method, params=None, timeout=40):
    url = f"{API}/{method}"
    data = urllib.parse.urlencode(params or {}).encode("utf-8")
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as resp:
        return json.loads(resp.read().decode("utf-8"))


def send(text, buttons=None):
    """Mesaj gonder. buttons: [[(etiket, callback_data), ...], ...]"""
    params = {
        "chat_id": config.TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }
    if buttons:
        params["reply_markup"] = json.dumps({
            "inline_keyboard": [
                [{"text": t, "callback_data": d} for (t, d) in row]
                for row in buttons
            ]
        })
    try:
        _api("sendMessage", params)
    except Exception as e:
        print(f"send hatasi: {e}")


def answer_callback(callback_id, text=""):
    try:
        _api("answerCallbackQuery", {"callback_query_id": callback_id, "text": text})
    except Exception as e:
        print(f"answer_callback hatasi: {e}")


# --- Menuler ---

def main_menu():
    send("🎵 <b>Ana Menu</b>\nNe yapmak istersin?", buttons=[
        [("🔄 Watchlist'i Senkronla", "sync_all")],
        [("📋 Listeler", "lists:0")],
        [("⚠️ Supheliler", "review_start")],
        [("❓ Yardim", "help")],
    ])


def lists_menu(sp, page=0):
    """Listeleri butonlarla goster (sayfali, 8'er)."""
    playlists = spc.list_playlists(sp)
    per = 8
    start = page * per
    chunk = playlists[start:start + per]
    buttons = [[(p["name"][:40], f"pl:{p['id']}")] for p in chunk]
    # Sayfalama
    nav = []
    if page > 0:
        nav.append(("⬅️ Onceki", f"lists:{page-1}"))
    if start + per < len(playlists):
        nav.append(("Sonraki ➡️", f"lists:{page+1}"))
    if nav:
        buttons.append(nav)
    buttons.append([("🏠 Ana Menu", "menu")])
    send(f"📋 <b>Listeler</b> (sayfa {page+1})\nBir liste sec:", buttons=buttons)


def playlist_menu(sp, pid):
    """Bir liste icin islem menusu."""
    playlists = spc.list_playlists(sp)
    p = next((x for x in playlists if x["id"] == pid), None)
    if not p:
        send("Liste bulunamadi.")
        return
    in_watch = pid in sync_module.read_watchlist()
    watch_label = "✅ Watchlist'te" if in_watch else "📌 Watchlist'e ekle"
    send(f"<b>{p['name']}</b>\n{p['track_count']} sarki", buttons=[
        [("🔄 Senkronla", f"sync:{pid}")],
        [("📥 Ilk dolum (hepsini aktar)", f"import:{pid}")],
        [("🔁 Mukerrer kontrol", f"dupes:{pid}")],
        [(watch_label, f"watch:{pid}")],
        [("🏠 Ana Menu", "menu")],
    ])


# --- Islemler ---

def do_sync(sp, yt, pid=None):
    playlists = spc.list_playlists(sp)
    if pid:
        target = next((x for x in playlists if x["id"] == pid), None)
        if not target:
            send("Liste bulunamadi.")
            return
        targets = [target]
        if sync_module.add_to_watchlist(pid):
            send(f"📌 '{target['name']}' watchlist'e eklendi.")
    else:
        watch_ids = sync_module.read_watchlist()
        targets = [p for p in playlists if p["id"] in watch_ids]
        if not targets:
            send("watchlist bos.")
            return

    send(f"🔄 Senkron basladi: {len(targets)} liste...")
    results = []
    for pl in targets:
        r = sync_module.sync_playlist(sp, yt, pl, sync_deletes=True)
        if r:
            results.append(r)

    changed = [r for r in results if r["added"] or r["removed"] or r["pending"]]
    if not changed:
        send("✅ Bitti. Degisiklik yok.")
        return
    lines = ["✅ Senkron bitti:", ""]
    for r in changed:
        parts = []
        if r["added"]: parts.append(f"+{r['added']}")
        if r["removed"]: parts.append(f"−{r['removed']}")
        if r["pending"]: parts.append(f"?{r['pending']}")
        lines.append(f"• <b>{r['name']}</b>: {', '.join(parts)}")
    send("\n".join(lines))


def do_import(sp, yt, pid):
    playlists = spc.list_playlists(sp)
    target = next((x for x in playlists if x["id"] == pid), None)
    if not target:
        send("Liste bulunamadi.")
        return
    send(f"📥 Ilk dolum: '{target['name']}' ({target['track_count']} sarki)...\n"
         f"Uzun surebilir, bitince haber veririm.")
    r = sync_module.sync_playlist(sp, yt, target, do_import=True)
    sync_module.add_to_watchlist(pid)
    if r:
        send(f"✅ '{r['name']}' aktarildi. +{r['added']} eklendi"
             + (f", ?{r['pending']} supheli" if r["pending"] else ""))
    else:
        send("Bitti.")


def do_dupes(sp, yt, pid):
    # pid bir SPOTIFY liste id'si; YouTube API'sine YouTube liste id'si vermeliyiz.
    # Once Spotify listesinin adini bul, sonra o ada karsilik gelen YT listesini cevir.
    playlists = spc.list_playlists(sp)
    sp_pl = next((x for x in playlists if x["id"] == pid), None)
    if not sp_pl:
        send("Liste bulunamadi.")
        return
    name = sp_pl["name"]
    # DB'de kayitli eslesme varsa onu kullan; yoksa (ya da ilk-gorulen yer tutucu
    # olarak Spotify id'si kaydedildiyse) isimden YouTube listesini bul.
    yt_pid = db.get_yt_playlist_for_spotify(pid)
    if not yt_pid or yt_pid == pid:
        yt_pid, _existed = sync_module._find_playlist(yt, name)
    if not yt_pid:
        send(f"'{name}' icin YouTube listesi bulunamadi "
             f"(bu liste henuz senkronlanmamis olabilir).")
        return
    try:
        pl = yt.get_playlist(yt_pid, limit=None)
    except Exception as e:
        # Bos liste ya da okunamayan liste -> ytmusicapi 'contents' hatasi verebilir
        msg = str(e)
        if "contents" in msg:
            send("Liste bos görünüyor (ya da hic sarki yok), mukerrer kontrolu yapilamadi.")
        else:
            send(f"Liste okunamadi: {msg[:200]}")
        return
    name = pl.get("title", "?")
    groups = defaultdict(list)
    for t in pl.get("tracks", []):
        title = t.get("title", "") or ""
        arts = t.get("artists") or []
        first = arts[0]["name"] if arts and arts[0].get("name") else ""
        key = f"{' '.join(title.lower().split())}|{' '.join(first.lower().split())}"
        groups[key].append((title, first))
    dups = {k: v for k, v in groups.items() if len(v) > 1}
    if not dups:
        send(f"✅ '{name}' temiz, mukerrer yok.")
        return
    extra = sum(len(v) - 1 for v in dups.values())
    lines = [f"⚠️ '{name}': {len(dups)} tekrar ({extra} fazladan):", ""]
    for k, v in sorted(dups.items(), key=lambda x: -len(x[1]))[:25]:
        lines.append(f"• {v[0][0]} [{v[0][1]}] x{len(v)}")
    lines.append("\nTemizlemek icin sunucuda: <code>python clean_duplicates.py \"" + name + "\"</code>")
    send("\n".join(lines))


# --- Review (butonlu) ---

def review_start(yt):
    pending = db.get_pending()
    if not pending:
        send("✅ Bekleyen supheli yok.")
        return
    _review_state["queue"] = [dict(r) for r in pending]
    _review_state["index"] = 0
    send(f"⚠️ {len(pending)} supheli eslesme var. Tek tek bakalim.")
    review_show(yt)


def review_show(yt):
    idx = _review_state["index"]
    queue = _review_state["queue"]
    if idx >= len(queue):
        send("✅ Tum supheliler islendi.")
        _review_state["queue"] = []
        return
    row = queue[idx]
    candidates = json.loads(row["candidates_json"]) if row.get("candidates_json") else []
    lines = [f"<b>{idx+1}/{len(queue)}</b>",
             f"🎵 {row['artist_name']} - {row['track_name']}",
             f"Sure: {row['spotify_duration']}s", "", "Adaylar:"]
    buttons = []
    for i, c in enumerate(candidates[:3], 1):
        tag = "🎵" if c.get("is_music") else "📹"
        lines.append(f"{i}. {tag} {c['artists']} - {c['title']} ({c.get('duration_sec','?')}s) skor={c.get('score','?')}")
        if c.get("videoId"):
            buttons.append([(f"{i}. adayi ekle", f"rev_pick:{idx}:{i-1}")])
    buttons.append([("⏭️ Atla", f"rev_skip:{idx}"), ("🗑️ Reddet", f"rev_reject:{idx}")])
    buttons.append([("🛑 Review'i bitir", "rev_stop")])
    send("\n".join(lines), buttons=buttons)


def review_pick(yt, idx, cand_idx):
    queue = _review_state["queue"]
    if idx >= len(queue):
        return
    row = queue[idx]
    candidates = json.loads(row["candidates_json"]) if row.get("candidates_json") else []
    if cand_idx >= len(candidates):
        send("Aday bulunamadi.")
        return
    c = candidates[cand_idx]
    if not c.get("videoId"):
        send("Bu adayin videoId'si yok.")
        return
    ok, already = ytc.add_to_playlist(yt, row["yt_playlist_id"], c["videoId"])
    if ok:
        db.mark_synced(row["spotify_track_id"], row["yt_playlist_id"],
                       c["videoId"], row["track_name"], row["artist_name"])
        db.remove_pending(row["id"])
        send(f"✅ Eklendi: {c['artists']} - {c['title']}")
    else:
        send("Ekleme basarisiz.")
    _review_state["index"] += 1
    review_show(yt)


def review_skip(yt, idx):
    _review_state["index"] += 1
    send("⏭️ Atlandi.")
    review_show(yt)


def review_reject(yt, idx):
    queue = _review_state["queue"]
    if idx < len(queue):
        db.remove_pending(queue[idx]["id"])
    _review_state["index"] += 1
    send("🗑️ Reddedildi.")
    review_show(yt)


# --- Callback yonlendirici ---

def handle_callback(data, callback_id, sp, yt):
    answer_callback(callback_id)
    if data == "menu":
        main_menu()
    elif data == "help":
        cmd_help()
    elif data == "sync_all":
        do_sync(sp, yt)
    elif data.startswith("lists:"):
        lists_menu(sp, int(data.split(":")[1]))
    elif data.startswith("pl:"):
        playlist_menu(sp, data.split(":", 1)[1])
    elif data.startswith("sync:"):
        do_sync(sp, yt, data.split(":", 1)[1])
    elif data.startswith("import:"):
        do_import(sp, yt, data.split(":", 1)[1])
    elif data.startswith("dupes:"):
        do_dupes(sp, yt, data.split(":", 1)[1])
    elif data.startswith("watch:"):
        pid = data.split(":", 1)[1]
        if sync_module.add_to_watchlist(pid):
            send("📌 Watchlist'e eklendi.")
        else:
            send("Zaten watchlist'te.")
    elif data == "review_start":
        review_start(yt)
    elif data.startswith("rev_pick:"):
        _, i, c = data.split(":")
        review_pick(yt, int(i), int(c))
    elif data.startswith("rev_skip:"):
        review_skip(yt, int(data.split(":")[1]))
    elif data.startswith("rev_reject:"):
        review_reject(yt, int(data.split(":")[1]))
    elif data == "rev_stop":
        _review_state["queue"] = []
        send("🛑 Review bitirildi.")


def cmd_help():
    send("<b>Komutlar:</b>\n\n"
         "/menu — buton menusu\n"
         "/sync — watchlist'i senkronla\n"
         "/sync 53 — '53'u senkronla + watchlist'e ekle\n"
         "/list — listeleri goster\n"
         "/review — supheli eslesmeler\n\n"
         "Veya /menu yazip butonlari kullan.")


# --- Metin komutlari ---

def handle_text(text, sp, yt):
    parts = text.strip().split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    if cmd in ("/menu", "menu", "/start"):
        main_menu()
    elif cmd in ("/sync", "sync"):
        if arg:
            playlists = spc.list_playlists(sp)
            t = next((p for p in playlists if p["name"].strip().lower() == arg.lower()), None)
            if not t:
                t = next((p for p in playlists if arg.lower() in p["name"].lower()), None)
            if not t:
                send(f"'{arg}' bulunamadi. /list ile bak.")
                return
            do_sync(sp, yt, t["id"])
        else:
            do_sync(sp, yt)
    elif cmd in ("/list", "list"):
        lists_menu(sp, 0)
    elif cmd in ("/review", "review"):
        review_start(yt)
    elif cmd in ("/help", "help"):
        cmd_help()
    else:
        send("Anlamadim. /menu yaz.")


def main():
    config.validate()
    if not config.TELEGRAM_TOKEN or not config.TELEGRAM_CHAT_ID:
        raise SystemExit("TELEGRAM_TOKEN ve TELEGRAM_CHAT_ID .env'de olmali.")
    db.init_db()

    print("Bot baslatiliyor... Spotify ve YouTube'a baglaniliyor.")
    sp = spc.get_client()
    yt = ytc.get_client()
    print("Bot hazir. (Ctrl+C ile durdur)")
    send("🤖 Bot aktif. /menu yaz.")

    offset = 0
    authorized = str(config.TELEGRAM_CHAT_ID)
    error_streak = 0  # arka arkaya ag hatasi sayaci

    while True:
        try:
            result = _api("getUpdates", {"offset": offset, "timeout": 30}, timeout=40)
            # Basarili istek -> uzun bir kesintiden cikildiysa haber ver
            if error_streak >= 5:
                print(f"Baglanti toparlandi ({error_streak} hatadan sonra).")
            error_streak = 0
        except Exception as e:
            error_streak += 1
            # Ilk birkac hatada kisa, sonra daha uzun bekle (ag bogulmasin)
            wait = 3 if error_streak < 5 else (10 if error_streak < 20 else 30)
            if error_streak <= 5 or error_streak % 10 == 0:
                print(f"getUpdates hatasi (#{error_streak}): {e} | {wait}s bekleniyor")
            time.sleep(wait)
            continue
        if not result or not result.get("ok"):
            time.sleep(3)
            continue

        for upd in result["result"]:
            offset = upd["update_id"] + 1
            # Buton tiklamasi mi?
            if "callback_query" in upd:
                cq = upd["callback_query"]
                chat = (cq.get("message") or {}).get("chat") or {}
                if str(chat.get("id")) != authorized:
                    continue
                try:
                    handle_callback(cq.get("data", ""), cq["id"], sp, yt)
                except Exception as e:
                    send(f"Hata: {e}")
                    print(f"callback hata: {e}")
                continue
            # Metin mesaji mi?
            msg = upd.get("message") or {}
            chat = msg.get("chat") or {}
            text = msg.get("text", "")
            if str(chat.get("id")) != authorized or not text:
                continue
            print(f"Komut: {text}")
            try:
                handle_text(text, sp, yt)
            except Exception as e:
                send(f"Hata: {e}")
                print(f"text hata: {e}")


if __name__ == "__main__":
    main()
