"""
Spotify listesindeki TEKRAR EDEN sarkilari listeler.
SADECE LISTELER - hicbir sey silmez/degistirmez.

Karsilastirma: sarki adi + ILK sanatci (kucuk harf, bosluk teklestirme).
Ayni isimli ama farkli sanatcili sarkilar mukerrer SAYILMAZ.

KULLANIM:
  python find_spotify_duplicates.py 22fTlkozEmPwN5IiVSX7tP
  python find_spotify_duplicates.py            (id vermezsen tum listeleri tarar)

Playlist id'lerini gormek icin: python sync.py --list
"""
import sys
from collections import defaultdict

import config
import spotify_client as spc


def norm(s):
    return " ".join((s or "").lower().split())


def simple_key(track):
    """Sarki adi + ilk sanatci."""
    first_artist = track["artists"].split(",")[0] if track.get("artists") else ""
    return f"{norm(track.get('name'))}|{norm(first_artist)}"


def scan_one(sp, playlist_id, name):
    tracks = spc.get_tracks(sp, playlist_id)
    groups = defaultdict(list)
    for t in tracks:
        groups[simple_key(t)].append(t)

    dups = {k: v for k, v in groups.items() if len(v) > 1}
    print(f"\n{'='*60}")
    print(f"'{name}'  -  {len(tracks)} sarki")
    if not dups:
        print("  Tekrar eden yok.")
        return 0

    extra = sum(len(v) - 1 for v in dups.values())
    print(f"  {len(dups)} sarki tekrar ediyor ({extra} fazladan kopya):")
    for key, items in sorted(dups.items(), key=lambda x: -len(x[1])):
        print(f"    '{items[0]['name']}'  x{len(items)}  [{items[0]['artists']}]")
    return extra


def main():
    config.validate()
    sp = spc.get_client()
    playlists = spc.list_playlists(sp)

    if len(sys.argv) > 1:
        pid = sys.argv[1]
        target = next((p for p in playlists if p["id"] == pid), None)
        if not target:
            raise SystemExit("Playlist bulunamadi. Id'yi 'python sync.py --list' ile kontrol et.")
        scan_one(sp, target["id"], target["name"])
    else:
        print("Tum listeler taraniyor (sadece tekrar icerenler raporlanir)...")
        total = 0
        for pl in playlists:
            total += scan_one(sp, pl["id"], pl["name"])
        print(f"\n{'='*60}\nToplam {total} fazladan kopya bulundu (tum listeler).")

    print("\n(Bu script hicbir sey silmedi, sadece listeledi.)")


if __name__ == "__main__":
    main()
