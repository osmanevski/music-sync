"""Dinleme gunlugu: YouTube gecmis dokumu + Spotify son dinlenenler -> SQLite.

Saf stdlib; ag/LLM cagrilari disaridan verilir (test edilebilir).
YouTube gecmisi zaman damgasi vermez: yeni girisler "ilk goruldugu" saatle kaydedilir.
Ilk calismada var olan gecmis kind='backfill' (pos = sira, 0 en yeni) olarak alinir.
"""
import datetime as dt
import json
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS videos(
    id TEXT PRIMARY KEY, title TEXT, duration REAL, first_seen TEXT,
    is_music INTEGER, artists TEXT, work TEXT, classified_at TEXT, classify_fails INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS tracks(
    id TEXT PRIMARY KEY, title TEXT, artists TEXT, album TEXT, duration_ms INTEGER);
CREATE TABLE IF NOT EXISTS plays(
    id INTEGER PRIMARY KEY, platform TEXT NOT NULL, item_id TEXT NOT NULL,
    played_at TEXT, seen_at TEXT, kind TEXT NOT NULL, pos INTEGER);
CREATE UNIQUE INDEX IF NOT EXISTS plays_timed ON plays(platform, item_id, played_at)
    WHERE played_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS plays_item ON plays(platform, item_id);
CREATE TABLE IF NOT EXISTS state(key TEXT PRIMARY KEY, value TEXT);
"""

ANCHOR_WINDOW = 3   # kac ardisik id eslesirse "eski yer" sayilir
ANCHOR_DEPTH = 40   # onceki listenin en ust kac ogesinde capa aranir


def now_iso():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def connect(path):
    db = sqlite3.connect(path)
    db.executescript(SCHEMA)
    return db


def get_state(db, key, default=None):
    row = db.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
    return json.loads(row[0]) if row else default


def set_state(db, key, value):
    db.execute("INSERT INTO state(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
               (key, json.dumps(value, ensure_ascii=False)))


def count_new_on_top(prev, cur, window=ANCHOR_WINDOW, depth=ANCHOR_DEPTH):
    """cur (en yeni basta) listesinin basindaki yeni giris sayisi; capa yoksa None.

    Capa: cur[k:k+w] dizisinin prev icinde (ilk `depth` oge) ardisik olarak gecmesi.
    YouTube ayni gun tekrar izlenen videoyu eski yerinden silip basa alir; bu yuzden capa
    aranirken cur[:k]'daki her id'nin prev'deki ilk gecisi cikarilir. O videolar yeni dinleme sayilir.
    """
    if not prev or not cur:
        return None
    for k in range(len(cur)):
        seg = cur[k:k + window]
        filtered = list(prev)
        for vid in cur[:k]:
            if vid in filtered[:depth]:
                filtered.remove(vid)
        if len(seg) < min(window, len(filtered)) or not filtered:
            break
        for cand in (prev, filtered):  # once silinme varsaymadan, sonra basa tasinmayla
            for j in range(min(depth, len(cand))):
                if cand[j:j + len(seg)] == seg:
                    return k
    return None


def ingest_youtube(db, dump, now=None):
    """Dokumu isler. Doner: {"new": n, "mode": first|live|gap|error, "error": ...}"""
    now = now or now_iso()
    if not dump or not dump.get("ok"):
        return {"new": 0, "mode": "error", "error": (dump or {}).get("error", "dokum yok"),
                "auth_error": bool((dump or {}).get("auth_error"))}
    items = dump["items"]
    cur = [i["id"] for i in items]
    for i in items:
        db.execute("INSERT INTO videos(id, title, duration, first_seen) VALUES(?, ?, ?, ?) "
                   "ON CONFLICT(id) DO UPDATE SET title=excluded.title, "
                   "duration=COALESCE(excluded.duration, videos.duration)",
                   (i["id"], i["title"], i.get("duration"), now))
    prev = get_state(db, "yt_prev")
    if prev is None:
        for pos, vid in enumerate(cur):
            db.execute("INSERT INTO plays(platform, item_id, played_at, seen_at, kind, pos) "
                       "VALUES('youtube', ?, NULL, NULL, 'backfill', ?)", (vid, pos))
        mode, new = "first", len(cur)
    else:
        k = count_new_on_top(prev, cur)
        mode = "live"
        if k is None:
            # Capa yok: bir saatte LIMIT'ten fazla izleme ya da gecmis silindi. Onceki listede
            # olmayan ust girisleri al, ilk tanidik id'de dur.
            known = set(prev)
            k = next((n for n, vid in enumerate(cur) if vid in known), len(cur))
            mode = "gap"
        for vid in cur[:k]:
            db.execute("INSERT INTO plays(platform, item_id, played_at, seen_at, kind) "
                       "VALUES('youtube', ?, NULL, ?, 'live')", (vid, now))
        new = k
    set_state(db, "yt_prev", cur)
    set_state(db, "yt_last_ok", now)
    return {"new": new, "mode": mode, "error": None, "auth_error": False}


def ingest_spotify(db, recent, now=None):
    """recent: Spotify /me/player/recently-played 'items' listesi. Doner: yeni dinleme sayisi."""
    now = now or now_iso()
    new = 0
    for it in recent or []:
        tr = it.get("track") or {}
        if not tr.get("id") or tr.get("type", "track") != "track":
            continue  # podcast bolumu / yerel dosya
        artists = [a.get("name") for a in tr.get("artists") or [] if a.get("name")]
        db.execute("INSERT INTO tracks(id, title, artists, album, duration_ms) VALUES(?, ?, ?, ?, ?) "
                   "ON CONFLICT(id) DO UPDATE SET title=excluded.title, artists=excluded.artists, "
                   "album=excluded.album, duration_ms=excluded.duration_ms",
                   (tr["id"], tr.get("name"), json.dumps(artists, ensure_ascii=False),
                    (tr.get("album") or {}).get("name"), tr.get("duration_ms")))
        cur = db.execute("INSERT OR IGNORE INTO plays(platform, item_id, played_at, seen_at, kind) "
                         "VALUES('spotify', ?, ?, ?, 'live')", (tr["id"], it.get("played_at"), now))
        new += cur.rowcount
    return new


def unclassified_videos(db, limit=40, max_fails=3):
    return db.execute("SELECT id, title, duration FROM videos WHERE classified_at IS NULL "
                      "AND classify_fails < ? ORDER BY first_seen DESC LIMIT ?", (max_fails, limit)).fetchall()


def apply_classification(db, results, asked_ids, now=None):
    """results: [{"id", "muzik", "sanatcilar", "eser"}]. Cevapsiz kalanlarin hata sayaci artar."""
    now = now or now_iso()
    done = set()
    for r in results:
        vid = r.get("id")
        if vid not in asked_ids or not isinstance(r.get("muzik"), bool):
            continue
        artists = [a.strip() for a in (r.get("sanatcilar") or []) if isinstance(a, str) and a.strip()]
        db.execute("UPDATE videos SET is_music=?, artists=?, work=?, classified_at=? WHERE id=?",
                   (int(r["muzik"]), json.dumps(artists, ensure_ascii=False) if r["muzik"] else None,
                    (r.get("eser") or None) if r["muzik"] else None, now, vid))
        done.add(vid)
    for vid in set(asked_ids) - done:
        db.execute("UPDATE videos SET classify_fails = classify_fails + 1 WHERE id=?", (vid,))
    return len(done)
