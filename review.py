"""
Supheli eslesmeleri elle inceleme araci.

Her supheli sarki icin en iyi 3 adayi gosterir, sen secersin:
  - Numara gir  -> o adayi ekle
  - s           -> atla (sonra bakarim)
  - x           -> kalici reddet (incelemeden cikar)

Kullanim:
  python review.py                 -> TUM listelerin supheliler
  python review.py <spotify_id>    -> SADECE o listenin supheliler
"""
import sys
import json

import config
import db
import ytmusic_client as ytc


def main():
    config.validate()
    db.init_db()

    # Arguman verilmisse, o Spotify listesine ait YouTube listesinin suphelilerini al
    yt_playlist_id = None
    if len(sys.argv) > 1:
        spotify_id = sys.argv[1]
        yt_playlist_id = db.get_yt_playlist_for_spotify(spotify_id)
        if not yt_playlist_id:
            print("Bu Spotify listesi icin kayit bulunamadi.")
            print("Once 'python sync.py --playlist <id>' ile senkronize etmis olmalisin.")
            return

    pending = db.get_pending(yt_playlist_id)

    if not pending:
        scope = "bu liste icin " if yt_playlist_id else ""
        print(f"{scope}Supheli eslesme yok. Her sey temiz.")
        return

    yt = ytc.get_client()
    scope = " (sadece bu liste)" if yt_playlist_id else ""
    print(f"{len(pending)} supheli eslesme var{scope}.\n")

    for row in pending:
        print("=" * 60)
        print(f"SPOTIFY: {row['artist_name']} - {row['track_name']}  "
              f"({row['spotify_duration']}s)")
        candidates = json.loads(row["candidates_json"])

        if not candidates:
            print("  Hic aday bulunamadi.")
        for i, c in enumerate(candidates, 1):
            tag = "MUZIK" if c.get("is_music") else "VIDEO"
            print(f"  [{i}] {c['artists']} - {c['title']}  "
                  f"({c['duration_sec']}s) [{tag}] skor={c['score']}")

        choice = input("Secim (numara / s=atla / x=reddet): ").strip().lower()

        if choice == "s":
            continue
        elif choice == "x":
            db.remove_pending(row["id"])
            print("  Reddedildi.")
        elif choice.isdigit() and 1 <= int(choice) <= len(candidates):
            c = candidates[int(choice) - 1]
            if not c.get("videoId"):
                print("  Bu adayin videoId'si yok, eklenemiyor.")
                continue
            ok, already = ytc.add_to_playlist(yt, row["yt_playlist_id"], c["videoId"])
            if ok:
                db.mark_synced(row["spotify_track_id"], row["yt_playlist_id"],
                               c["videoId"], row["track_name"], row["artist_name"])
                db.remove_pending(row["id"])
                print("  Eklendi ve kaydedildi." + (" (zaten vardi)" if already else ""))
            else:
                print("  Ekleme basarisiz, supheli kaldi.")
        else:
            print("  Gecersiz secim, atlandi.")


if __name__ == "__main__":
    main()
