"""Ozan · Akis: dinleme gunlugunden parca secimi ve YouTube listesi istegi (hermes kullanicisi).

    python -m dinleme.akis oneri [--n 50] [--gun 14]      # puanli aday listesi
    python -m dinleme.akis istek [--n 50] [--ids a,b,c]  # listeyi yazdirir, root yardimcisini bekler

Liste YouTube'a root tarafindaki `dinleme.yt_liste` yazar (Google cerezleri yalniz root'ta).
Puan: her dinleme yakinligina gore agirlik alir (yari omur --gun). Sanatci tavani YOK (Osman).
"""
import argparse
import datetime as dt
import json
import os
import sqlite3
import sys
import time

DATA = os.environ.get("OZAN_DATA", "/var/lib/hermes/profiles/ozan/data")
DB = os.path.join(DATA, "dinleme.db")
REQUEST = os.path.join(DATA, "akis-istek.json")
RESULT = os.path.join(DATA, "akis-sonuc.json")
TITLE = "Ozan · Akış"
MAX_DURATION = 900       # 15 dk ustu: tam bolum/konser, radyoya uygun degil
BACKFILL_SPAN = 100      # ilk yuklemede pos 100 ~ bir yari omur kadar eski sayilir


def _age_days(seen_at, now):
    try:
        t = dt.datetime.fromisoformat(seen_at)
    except (TypeError, ValueError):
        return None
    return max(0.0, (now - t).total_seconds() / 86400)


def score(db, half_life=14.0, now=None, max_duration=MAX_DURATION):
    now = now or dt.datetime.now(dt.timezone.utc)
    rows = db.execute(
        "SELECT p.item_id, p.kind, p.seen_at, p.pos, v.title, v.artists, v.work, v.duration "
        "FROM plays p JOIN videos v ON v.id = p.item_id "
        "WHERE p.platform='youtube' AND v.is_music=1").fetchall()
    out = {}
    for vid, kind, seen_at, pos, title, artists, work, duration in rows:
        if duration and duration > max_duration:
            continue
        if kind == "backfill":
            w = 0.5 ** ((pos or 0) / BACKFILL_SPAN)
        else:
            age = _age_days(seen_at, now)
            w = 0.5 ** ((age or 0) / half_life)
        e = out.setdefault(vid, {"id": vid, "title": title, "artists": json.loads(artists or "[]"),
                                 "work": work, "score": 0.0, "plays": 0})
        e["score"] += w
        e["plays"] += 1
    return sorted(out.values(), key=lambda e: (-e["score"], -e["plays"], e["id"]))


def pick(db, n=50, **kw):
    return score(db, **kw)[:n]


def write_request(ids, title=TITLE, path=REQUEST):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"title": title, "video_ids": ids, "at": time.time()}, f)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def wait_result(since, path=RESULT, timeout=240):
    end = time.time() + timeout
    while time.time() < end:
        try:
            with open(path, encoding="utf-8") as f:
                r = json.load(f)
            if r.get("request_at", 0) >= since:
                return r
        except (OSError, ValueError):
            pass
        time.sleep(3)
    return None


def main(argv):
    ap = argparse.ArgumentParser(prog="dinleme.akis")
    ap.add_argument("komut", choices=["oneri", "istek"])
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--gun", type=float, default=14.0, help="yari omur (gun)")
    ap.add_argument("--ids", help="virgulle video id'leri (Ozan'in elle secimi)")
    ap.add_argument("--baslik", default=TITLE)
    a = ap.parse_args(argv)
    db = sqlite3.connect(DB)
    if a.komut == "oneri":
        for i, e in enumerate(pick(db, a.n, half_life=a.gun), 1):
            print(f"{i:2}. {', '.join(e['artists']) or '?'} - {e['work'] or e['title']} "
                  f"[{e['id']}] puan={e['score']:.2f} dinleme={e['plays']}")
        return 0
    ids = [x.strip() for x in a.ids.split(",") if x.strip()] if a.ids else \
        [e["id"] for e in pick(db, a.n, half_life=a.gun)]
    if not ids:
        print("HATA: secilecek muzik dinlemesi yok")
        return 1
    since = time.time()
    write_request(ids, a.baslik)
    r = wait_result(since)
    if not r:
        print("HATA: YouTube liste yardimcisi 4 dakikada cevap vermedi (music-sync-akis.service)")
        return 1
    if not r.get("ok"):
        print(f"HATA: {r.get('error')}")
        return 1
    print(f"tamam: '{r['title']}' {r['added']} parca, eksik {len(r.get('missing') or [])}")
    print(f"url: {r['url']}")
    print("radyoya gecirmek icin: python3 -m dinleme.radyo islem save_playlist name=... ; "
          f"python3 -m dinleme.radyo islem refresh url={r['url']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
