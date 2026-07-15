"""
SQLite veritabani. Iki sey takip eder:
  1. synced_tracks: basariyla eklenmis sarkilar (tekrar eklemeyi onler, kotayi/zamani korur)
  2. pending_review: supheli eslesmeler (sen onaylayana kadar bekler)
  3. playlist_snapshots: Spotify playlist snapshot_id'leri (degismemisse atla)
"""
import sqlite3
from contextlib import contextmanager
import config


@contextmanager
def get_db():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS synced_tracks (
            spotify_track_id TEXT,
            yt_playlist_id   TEXT,
            yt_video_id      TEXT,
            track_name       TEXT,
            artist_name      TEXT,
            synced_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (spotify_track_id, yt_playlist_id)
        );

        CREATE TABLE IF NOT EXISTS pending_review (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            spotify_track_id TEXT,
            yt_playlist_id   TEXT,
            track_name       TEXT,
            artist_name      TEXT,
            spotify_duration INTEGER,
            candidates_json  TEXT,   -- en iyi adaylar JSON olarak
            created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (spotify_track_id, yt_playlist_id)
        );

        CREATE TABLE IF NOT EXISTS playlist_snapshots (
            spotify_playlist_id TEXT PRIMARY KEY,
            snapshot_id         TEXT,
            yt_playlist_id      TEXT,
            updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- Bir Spotify listesinde EN SON gordugumuz track id'leri.
        -- Yeni eklenenleri tespit etmek icin onceki hal ile kiyaslariz.
        CREATE TABLE IF NOT EXISTS playlist_track_state (
            spotify_playlist_id TEXT,
            spotify_track_id    TEXT,
            PRIMARY KEY (spotify_playlist_id, spotify_track_id)
        );

        -- Ters yon (YouTube -> Spotify) tamamen ayri tutulur.
        CREATE TABLE IF NOT EXISTS reverse_playlist_state (
            yt_playlist_id TEXT,
            yt_video_id    TEXT,
            PRIMARY KEY (yt_playlist_id, yt_video_id)
        );

        CREATE TABLE IF NOT EXISTS reverse_synced_tracks (
            yt_playlist_id     TEXT,
            yt_video_id        TEXT,
            spotify_playlist_id TEXT,
            spotify_track_id   TEXT,
            track_name         TEXT,
            artist_name        TEXT,
            synced_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (yt_playlist_id, yt_video_id, spotify_playlist_id)
        );
        """)


def is_synced(spotify_track_id, yt_playlist_id):
    with get_db() as conn:
        row = conn.execute(
            "SELECT 1 FROM synced_tracks WHERE spotify_track_id=? AND yt_playlist_id=?",
            (spotify_track_id, yt_playlist_id)
        ).fetchone()
        return row is not None


def mark_synced(spotify_track_id, yt_playlist_id, yt_video_id, track_name, artist_name):
    with get_db() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO synced_tracks
               (spotify_track_id, yt_playlist_id, yt_video_id, track_name, artist_name)
               VALUES (?,?,?,?,?)""",
            (spotify_track_id, yt_playlist_id, yt_video_id, track_name, artist_name)
        )


def add_pending(spotify_track_id, yt_playlist_id, track_name, artist_name,
                spotify_duration, candidates_json):
    with get_db() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO pending_review
               (spotify_track_id, yt_playlist_id, track_name, artist_name,
                spotify_duration, candidates_json)
               VALUES (?,?,?,?,?,?)""",
            (spotify_track_id, yt_playlist_id, track_name, artist_name,
             spotify_duration, candidates_json)
        )


def get_pending(yt_playlist_id=None):
    with get_db() as conn:
        if yt_playlist_id:
            return conn.execute(
                "SELECT * FROM pending_review WHERE yt_playlist_id=? ORDER BY created_at",
                (yt_playlist_id,)
            ).fetchall()
        return conn.execute(
            "SELECT * FROM pending_review ORDER BY created_at"
        ).fetchall()


def get_yt_playlist_for_spotify(spotify_playlist_id):
    """Spotify liste id'sinden, ona karsilik gelen YouTube liste id'sini bul."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT yt_playlist_id FROM playlist_snapshots WHERE spotify_playlist_id=?",
            (spotify_playlist_id,)
        ).fetchone()
        return row["yt_playlist_id"] if row else None


def get_synced_for_playlist(yt_playlist_id):
    """Bu YouTube listesine BIZIM ekledigimiz (DB'de kayitli) sarkilari dondur.
    Donen: [{spotify_track_id, yt_video_id, track_name, artist_name}]"""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT spotify_track_id, yt_video_id, track_name, artist_name
               FROM synced_tracks WHERE yt_playlist_id=?""",
            (yt_playlist_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def remove_synced(spotify_track_id, yt_playlist_id):
    """Bir sarkiyi synced kaydindan sil (YouTube'dan silindiginde)."""
    with get_db() as conn:
        conn.execute(
            "DELETE FROM synced_tracks WHERE spotify_track_id=? AND yt_playlist_id=?",
            (spotify_track_id, yt_playlist_id)
        )


def remove_pending(pending_id):
    with get_db() as conn:
        conn.execute("DELETE FROM pending_review WHERE id=?", (pending_id,))


def get_snapshot(spotify_playlist_id):
    with get_db() as conn:
        row = conn.execute(
            "SELECT snapshot_id FROM playlist_snapshots WHERE spotify_playlist_id=?",
            (spotify_playlist_id,)
        ).fetchone()
        return row["snapshot_id"] if row else None


def set_snapshot(spotify_playlist_id, snapshot_id, yt_playlist_id):
    with get_db() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO playlist_snapshots
               (spotify_playlist_id, snapshot_id, yt_playlist_id, updated_at)
               VALUES (?,?,?,CURRENT_TIMESTAMP)""",
            (spotify_playlist_id, snapshot_id, yt_playlist_id)
        )


def get_track_state(spotify_playlist_id):
    """Bu listede EN SON gordugumuz Spotify track id'lerini kume olarak dondur.
    Hic kayit yoksa None dondur (ilk kez goruluyor demektir)."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT spotify_track_id FROM playlist_track_state WHERE spotify_playlist_id=?",
            (spotify_playlist_id,)
        ).fetchall()
        if not rows:
            return None
        return {r["spotify_track_id"] for r in rows}


def set_track_state(spotify_playlist_id, track_ids):
    """Bu listenin guncel track id'lerini kaydet (eskisini silip yenisini yaz)."""
    with get_db() as conn:
        conn.execute(
            "DELETE FROM playlist_track_state WHERE spotify_playlist_id=?",
            (spotify_playlist_id,)
        )
        conn.executemany(
            "INSERT OR IGNORE INTO playlist_track_state (spotify_playlist_id, spotify_track_id) VALUES (?,?)",
            [(spotify_playlist_id, tid) for tid in track_ids]
        )


def get_reverse_track_state(yt_playlist_id):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT yt_video_id FROM reverse_playlist_state WHERE yt_playlist_id=?",
            (yt_playlist_id,)
        ).fetchall()
        if not rows:
            return None
        return {r["yt_video_id"] for r in rows}


def set_reverse_track_state(yt_playlist_id, video_ids):
    with get_db() as conn:
        conn.execute(
            "DELETE FROM reverse_playlist_state WHERE yt_playlist_id=?", (yt_playlist_id,)
        )
        conn.executemany(
            "INSERT OR IGNORE INTO reverse_playlist_state (yt_playlist_id, yt_video_id) VALUES (?,?)",
            [(yt_playlist_id, vid) for vid in video_ids]
        )


def mark_reverse_synced(yt_playlist_id, yt_video_id, spotify_playlist_id,
                        spotify_track_id, track_name, artist_name):
    with get_db() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO reverse_synced_tracks
               (yt_playlist_id, yt_video_id, spotify_playlist_id, spotify_track_id,
                track_name, artist_name) VALUES (?,?,?,?,?,?)""",
            (yt_playlist_id, yt_video_id, spotify_playlist_id, spotify_track_id,
             track_name, artist_name)
        )


def get_reverse_synced(yt_playlist_id, spotify_playlist_id):
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM reverse_synced_tracks
               WHERE yt_playlist_id=? AND spotify_playlist_id=?""",
            (yt_playlist_id, spotify_playlist_id)
        ).fetchall()
        return [dict(r) for r in rows]


def remove_reverse_synced(yt_playlist_id, yt_video_id, spotify_playlist_id):
    with get_db() as conn:
        conn.execute(
            """DELETE FROM reverse_synced_tracks
               WHERE yt_playlist_id=? AND yt_video_id=? AND spotify_playlist_id=?""",
            (yt_playlist_id, yt_video_id, spotify_playlist_id)
        )
