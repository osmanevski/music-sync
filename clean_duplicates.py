"""
YouTube Music listesindeki tekrar eden sarkilari temizler.

IKI DURUM:
  1. Ayni isim + AYNI sanatci  -> KESIN mukerrer.
     Ilk kopya korunur, fazlalik(lar) otomatik silinir (sormadan).
  2. Ayni isim + FARKLI sanatci -> SUPHELI.
     Sana sorar: hepsini tut, ya da hangilerini silecegini sec.

GUVENLIK: Once neyin otomatik silinecegini gosterir.
Supheli gruplar icin tek tek sorar. En sonda toplam onay alir.
'evet' demezsen hicbir sey silinmez.

KULLANIM:
  python clean_duplicates.py 42
  python clean_duplicates.py "Liste Adi"
"""
import sys
from collections import defaultdict

import config
import ytmusic_client as ytc


def norm(s):
    return " ".join((s or "").lower().split())


def title_key(track):
    return norm(track.get("title", ""))


def first_artist(track):
    artists = track.get("artists") or []
    return artists[0]["name"] if artists and artists[0].get("name") else ""


def artist_str(track):
    return ", ".join(a["name"] for a in (track.get("artists") or []) if a.get("name"))


def removable(track):
    return bool(track.get("videoId") and track.get("setVideoId"))


def find_playlist_id(yt, name_or_id):
    try:
        playlists = yt.get_library_playlists(limit=100)
    except Exception:
        playlists = []
    for pl in playlists:
        if pl.get("title") == name_or_id:
            return pl["playlistId"], pl["title"]
    return name_or_id, name_or_id


def main():
    if len(sys.argv) < 2:
        raise SystemExit('Kullanim: python clean_duplicates.py "liste adi"')

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
    print(f"Toplam {len(tracks)} sarki.\n")

    by_title = defaultdict(list)
    for t in tracks:
        by_title[title_key(t)].append(t)

    to_remove = []
    suspicious_groups = []

    for tkey, items in by_title.items():
        if len(items) < 2:
            continue

        by_artist = defaultdict(list)
        for it in items:
            by_artist[norm(first_artist(it))].append(it)

        for akey, alist in by_artist.items():
            if len(alist) > 1:
                for extra in alist[1:]:
                    if removable(extra):
                        to_remove.append(extra)

        if len(by_artist) > 1:
            suspicious_groups.append((items[0].get("title", ""), by_artist))

    print("=" * 60)
    if to_remove:
        print(f"KESIN MUKERRER (ayni isim+sanatci) - otomatik silinecek: {len(to_remove)}\n")
        shown = defaultdict(int)
        for t in to_remove:
            shown[f"{t.get('title')} [{artist_str(t)}]"] += 1
        for label, n in shown.items():
            print(f"    - {label}  x{n} fazladan")
    else:
        print("Kesin mukerrer yok.")
    print("=" * 60)

    if suspicious_groups:
        print(f"\n{len(suspicious_groups)} sarki adinda FARKLI sanatcilar var.")
        print("Bunlara tek tek karar vereceksin.\n")

        for title, by_artist in suspicious_groups:
            print("-" * 60)
            print(f"'{title}' altinda farkli sanatcilar:")
            options = []
            idx = 1
            for akey, alist in by_artist.items():
                for it in alist:
                    options.append(it)
                    extra = "" if removable(it) else "  (silinemez - id yok)"
                    print(f"  [{idx}] {it.get('title')} [{artist_str(it)}]{extra}")
                    idx += 1
            print("  [t] hepsini tut (hicbirini silme)")
            secim = input("Silmek istediklerinin numaralarini virgulle yaz (orn 2,3) / t: ").strip().lower()

            if secim == "t" or not secim:
                print("  Hepsi tutuldu.")
                continue
            try:
                picks = [int(x) for x in secim.replace(" ", "").split(",") if x]
            except ValueError:
                print("  Gecersiz giris, bu grup atlandi (silinmedi).")
                continue
            for p in picks:
                if 1 <= p <= len(options):
                    it = options[p - 1]
                    if removable(it):
                        to_remove.append(it)
                        print(f"    silinecek: {it.get('title')} [{artist_str(it)}]")
                    else:
                        print(f"    atlandi (id yok): {it.get('title')}")

    if not to_remove:
        print("\nSilinecek bir sey yok. Liste oldugu gibi kaliyor.")
        return

    print("\n" + "=" * 60)
    print(f"TOPLAM {len(to_remove)} sarki SILINECEK. Bu islem GERI ALINAMAZ.")
    cevap = input("Onayliyor musun? Silmek icin 'evet' yaz: ").strip().lower()
    if cevap != "evet":
        print("Iptal edildi. Hicbir sey silinmedi.")
        return

    try:
        yt.remove_playlist_items(playlist_id, to_remove)
        print(f"Tamam. {len(to_remove)} sarki silindi.")
    except Exception as e:
        print(f"Silme sirasinda hata: {e}")
        print("Liste kismen degismis olabilir, tekrar calistirip kontrol et.")


if __name__ == "__main__":
    main()
