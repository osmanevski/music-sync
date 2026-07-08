"""
YouTube Music listesindeki TEKRAR EDEN sarkilari listeler.
SADECE LISTELER - hicbir sey silmez, degistirmez.

Karsilastirma basit: sarki adi (kucuk harfe cevrilip bosluk kirpilmis hali)
ayni olanlari ayni grup sayar. Sanatci/sure'ye bakmaz - sen oyle istedin.

KULLANIM:
  python find_duplicates.py "18"
  python find_duplicates.py 22fTlkozEmPwN5IiVSX7tP   (playlist id de olur)

Liste adi YouTube'daki adla birebir ayni olmali (tirnak icinde yaz).
"""
import sys
from collections import defaultdict

import config
import ytmusic_client as ytc


def simple_key(track):
    """Sarki adi + ILK sanatci. Ayni isimli farkli sanatcilar mukerrer SAYILMAZ."""
    title = track.get("title", "") or ""
    artists = track.get("artists") or []
    first_artist = artists[0]["name"] if artists and artists[0].get("name") else ""
    t = " ".join(title.lower().split())
    a = " ".join(first_artist.lower().split())
    return f"{t}|{a}"


def find_playlist_id(yt, name_or_id):
    """Verilen deger bir isim mi id mi? Isimse id'sini bul."""
    # Once kutuphanedeki listelerde isim olarak ara
    try:
        playlists = yt.get_library_playlists(limit=100)
    except Exception:
        playlists = []
    for pl in playlists:
        if pl.get("title") == name_or_id:
            return pl["playlistId"], pl["title"]
    # Bulunamadiysa, verilen degeri dogrudan id kabul et
    return name_or_id, name_or_id


def main():
    if len(sys.argv) < 2:
        raise SystemExit('Kullanim: python find_duplicates.py "liste adi"')

    name_or_id = sys.argv[1]
    config.validate()
    yt = ytc.get_client()

    playlist_id, display_name = find_playlist_id(yt, name_or_id)
    print(f"Liste taraniyor: '{display_name}'\n")

    try:
        pl = yt.get_playlist(playlist_id, limit=None)
    except Exception as e:
        raise SystemExit(f"Liste okunamadi: {e}")

    tracks = pl.get("tracks", [])
    print(f"Toplam {len(tracks)} sarki bulundu.\n")

    # Sarki adi + sanatci'ya gore grupla
    groups = defaultdict(list)
    for t in tracks:
        title = t.get("title", "") or ""
        artists = ", ".join(
            a["name"] for a in (t.get("artists") or []) if a.get("name")
        )
        key = simple_key(t)
        groups[key].append((title, artists))

    # Sadece birden fazla olanlari (tekrar edenleri) goster
    duplicates = {k: v for k, v in groups.items() if len(v) > 1}

    if not duplicates:
        print("Tekrar eden sarki yok. Liste temiz.")
        return

    total_extra = sum(len(v) - 1 for v in duplicates.values())
    print(f"{len(duplicates)} sarki adi tekrar ediyor "
          f"(toplam {total_extra} fazladan kopya):\n")
    print("=" * 60)
    for key, items in sorted(duplicates.items(), key=lambda x: -len(x[1])):
        print(f"\n'{items[0][0]}'  ->  {len(items)} kez:")
        for title, artists in items:
            print(f"    - {title}  [{artists}]")
    print("\n" + "=" * 60)
    print("(Bu script hicbir sey silmedi, sadece listeledi.)")


if __name__ == "__main__":
    main()
