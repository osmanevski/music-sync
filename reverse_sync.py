"""YouTube Music playlist'lerini Spotify'a guvenli ve fark-bazli senkronlar."""
import argparse

import config
import db
import matcher
import spotify_client as spc
import ytmusic_client as ytc


def sync_playlist(sp, yt, yt_playlist, dry_run=False, sync_deletes=True):
    yt_pid = yt_playlist["id"]
    name = yt_playlist["name"]
    tracks = ytc.get_tracks(yt, yt_pid)
    current_ids = {t["id"] for t in tracks}
    previous_ids = db.get_reverse_track_state(yt_pid)

    # Ilk calisma kullanici acisindan import'tur; hedefte olanlar tekrar eklenmez.
    new_ids = current_ids if previous_ids is None else current_ids - previous_ids
    removed_ids = set() if previous_ids is None or not sync_deletes else previous_ids - current_ids

    if dry_run:
        existing = next((p for p in spc.list_playlists(sp) if p["name"] == name), None)
        sp_pid = existing["id"] if existing else None
    else:
        sp_pid, _ = spc.get_or_create_playlist(sp, name)

    existing_tracks = spc.get_tracks(sp, sp_pid) if sp_pid else []
    existing_keys = {matcher.track_key(t["name"], t["artists"]) for t in existing_tracks}

    added = skipped = pending = removed = 0
    pending_ids = set()
    for track in (t for t in tracks if t["id"] in new_ids):
        key = matcher.track_key(track["name"], track["artists"])
        if key and key in existing_keys:
            skipped += 1
            continue
        candidates = spc.search_tracks(sp, track["name"], track["artists"])
        best, score, _ = matcher.best_match(track, candidates)
        if not best or score < config.MIN_CONFIDENCE_SCORE:
            pending += 1
            pending_ids.add(track["id"])
            print(f"  ? SUPHELI: {track['artists']} - {track['name']} (skor {score})")
            continue
        if dry_run:
            added += 1
            print(f"  + (EKLENECEKTI) {best['artists']} - {best['title']} (skor {score})")
        elif spc.add_to_playlist(sp, sp_pid, best["spotify_id"]):
            db.mark_reverse_synced(
                yt_pid, track["id"], sp_pid, best["spotify_id"],
                track["name"], track["artists"]
            )
            existing_keys.add(key)
            added += 1

    if sp_pid and removed_ids:
        ours = {r["yt_video_id"]: r for r in db.get_reverse_synced(yt_pid, sp_pid)}
        for video_id in removed_ids:
            rec = ours.get(video_id)
            if not rec:
                continue
            if dry_run:
                removed += 1
            elif spc.remove_from_playlist(sp, sp_pid, rec["spotify_track_id"]):
                db.remove_reverse_synced(yt_pid, video_id, sp_pid)
                removed += 1

    if not dry_run:
        # Suphelileri tamamlanmis sayma; sonraki calismada yeniden aransinlar.
        db.set_reverse_track_state(yt_pid, current_ids - pending_ids)
    print(f"[YT -> Spotify] {name}: +{added}, -{removed}, ?{pending}, ={skipped}")
    return {"name": name, "added": added, "removed": removed,
            "pending": pending, "skipped": skipped}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", action="store_true", help="YouTube Music listelerini goster")
    parser.add_argument("--playlist", help="Tek YouTube Music playlist id'si")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-delete", action="store_true")
    args = parser.parse_args()

    config.validate()
    db.init_db()
    sp, yt = spc.get_client(), ytc.get_client()
    playlists = ytc.list_playlists(yt)
    if args.list:
        for pl in playlists:
            print(f"  {pl['id']}  {pl['name']}  ({pl['track_count']} sarki)")
        return
    if not args.playlist:
        parser.error("--playlist gerekli (once --list ile ID'yi bulun)")
    target = next((p for p in playlists if p["id"] == args.playlist), None)
    if not target:
        raise SystemExit("YouTube Music playlist bulunamadi.")
    sync_playlist(sp, yt, target, dry_run=args.dry_run,
                  sync_deletes=not args.no_delete)


if __name__ == "__main__":
    main()
