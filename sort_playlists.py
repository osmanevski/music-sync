"""
Spotify listelerini added_at'e gore (en yeni en ustte) yeniden dizer.
sync.py'den cagrilir; tek basina da calisir:
    python sort_playlists.py --list            # sort_watchlist.txt'tekileri goster
    python sort_playlists.py --dry-run         # kac hamle gerekir
    python sort_playlists.py                   # sirala
Hangi listeler: sort_watchlist.txt (her satira bir playlist id, # yorum). Dosya yoksa/bossa hicbir sey yapmaz.
Sadece sahibi oldugun (veya collaborative) listeler siralanabilir.
"""
import os
import sys
import time
import spotify_client as spc

SORT_FILE = "sort_watchlist.txt"
# Spotify, kısa sürede binlerce reorder isteğine saatlerce süren rate limit (Retry-After ~8 saat)
# veriyor. Her çalışmada liste başına en fazla MAX_MOVES taşıma yapılır, aralarında PAUSE beklenir.
# Taşımalar en üstten başladığı için yarım bırakılan sıralama da geçerlidir; kalan kısım sonraki
# çalışmada (her gece sync sonunda) devam eder.
MAX_MOVES = int(os.environ.get("SORT_MAX_MOVES", "300"))
PAUSE = float(os.environ.get("SORT_PAUSE_SECONDS", "0.3"))
# Elle, anlamli bir sirayla dizilmis listeler: sort_watchlist.txt'e eklense bile asla siralanmaz.
# Liste adinda geciyorsa korunur; buyuk/kucuk harf ve ı/i farki yok sayilir ("ϟ FIRTINA" da korunur).
PROTECTED_NAMES = {"fırtına"}


def _norm(s):
    return (s or "").casefold().replace("ı", "i").replace("i\u0307", "i")


def is_protected(name):
    return any(_norm(p) in _norm(name) for p in PROTECTED_NAMES)


def read_sort_ids():
    if not os.path.exists(SORT_FILE):
        return set()
    ids = set()
    with open(SORT_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                ids.add(line)
    return ids


def get_added_dates(sp, pid):
    dates = []
    page = sp.playlist_items(pid, fields="items(added_at),next", limit=100,
                             additional_types=["track", "episode"])
    while page:
        dates += [(i.get("added_at") or "") for i in page["items"]]
        page = sp.next(page) if page.get("next") else None
    return dates


def plan_moves(dates):
    """[(range_start, insert_before)] -- en yeni en uste. Esit tarihlerde mevcut sira korunur."""
    n = len(dates)
    current = list(range(n))
    target = sorted(range(n), key=lambda i: dates[i], reverse=True)
    moves = []
    for i, want in enumerate(target):
        j = current.index(want)
        if j != i:
            moves.append((j, i))
            current.insert(i, current.pop(j))
    return moves


def sort_playlist(sp, pl, dry_run=False):
    pid, name = pl["id"], pl["name"]
    if is_protected(name):
        print(f"[SIRA] '{name}' korumali (elle sirali), atlandi.")
        return 0
    dates = get_added_dates(sp, pid)
    moves = plan_moves(dates)
    if not moves:
        print(f"[SIRA] '{name}' zaten sirali.")
        return 0
    print(f"[SIRA] '{name}': {len(dates)} parca, {len(moves)} hamle" + (" (kuru)" if dry_run else ""))
    if dry_run:
        return len(moves)
    batch = moves[:MAX_MOVES]
    if len(batch) < len(moves):
        print(f"  bu calismada ilk {len(batch)} hamle; kalan {len(moves) - len(batch)} sonraki calismada")
    snap = spc.get_playlist_snapshot(sp, pid)
    for n, (j, i) in enumerate(batch):
        if n:
            time.sleep(PAUSE)
        res = sp.playlist_reorder_items(pid, range_start=j, insert_before=i,
                                        range_length=1, snapshot_id=snap)
        snap = (res or {}).get("snapshot_id", snap)
    return len(batch)


def sort_targets(sp, playlists, dry_run=False):
    """sync.py hook'u. Hata verirse senkronu bozmaz."""
    ids = read_sort_ids()
    for pl in playlists:
        if pl["id"] not in ids:
            continue
        try:
            sort_playlist(sp, pl, dry_run)
        except Exception as e:
            print(f"  ! Siralama hatasi '{pl['name']}': {e}")


if __name__ == "__main__":
    sp = spc.get_client()
    pls = [p for p in spc.list_playlists(sp) if p["id"] in read_sort_ids()]
    if "--list" in sys.argv:
        for p in pls:
            print(p["id"], p["name"], p["track_count"])
    else:
        sort_targets(sp, pls, dry_run="--dry-run" in sys.argv)
