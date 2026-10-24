"""
Music Sync durumu — salt-okunur sorgu araci (Hermes ve elle kullanim icin).

Hicbir sey yazmaz, Spotify'a ya da YouTube'a istek atmaz; yalniz sync.db'yi
salt-okunur acar ve gece senkronunun kaydettigi son calisma logunu okur.

  python3 durum.py ozet              son gece senkronu + liste basina sayilar
  python3 durum.py ara "<metin>"     sarki/sanatci: YouTube'a gecti mi, inceleme mi bekliyor
  python3 durum.py bekleyen [liste]  inceleme bekleyen supheli eslesmeler

Tek yazan alt komut `kaydet`tir ve yalniz root'un gece senkronu bittiginde
(ExecStopPost) calistirmasi icindir: o calismanin journal'ini ve liste adlarini
DURUM_DIR'e koyar. Liste adlari Spotify API'sinden degil, kimliksiz oEmbed'den
gelir; Music Sync'in istek kotasina dokunmaz.
"""
import json
import os
import re
import sqlite3
import subprocess
import sys
import unicodedata
import urllib.request
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("MUSIC_SYNC_DB", HERE / "sync.db"))
DURUM_DIR = Path(os.environ.get("MUSIC_SYNC_DURUM_DIR", "/var/lib/music-sync-durum"))
LOG_KEEP = 14


# --- ortak -------------------------------------------------------------------

def norm(s):
    """Turkce duyarli, aksan ve buyuk/kucuk harf farkini yok sayan karsilastirma anahtari."""
    s = (s or "").replace("I", "ı").replace("İ", "i").casefold().replace("ı", "i")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).strip()


def open_db(path=None):
    path = Path(path or DB_PATH)
    if not path.exists():
        raise SystemExit(f"sync.db bulunamadi: {path}")
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def playlist_names(durum_dir=None):
    """yt_playlist_id -> ad. kaydet'in yazdigi listeler.json'dan."""
    f = Path(durum_dir or DURUM_DIR) / "listeler.json"
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {v["yt"]: v.get("ad") or sp for sp, v in data.items() if v.get("yt")}


def label(yt_id, names):
    return names.get(yt_id) or f"(adı bilinmiyor: {yt_id})"


# --- son calisma logu --------------------------------------------------------

def parse_run(text):
    """Gece senkronu logundan ozet cikarir."""
    out = {"baslangic": None, "bitis": None, "bitti": False, "listeler": [],
           "eklenen": [], "supheli": [], "silinen": [], "sira": [], "hatalar": []}
    current = None
    for raw in text.splitlines():
        m = re.match(r"^(\S+)\s+\S+\s+[^:]+:\s?(.*)$", raw)
        ts, line = (m.group(1), m.group(2)) if m else (None, raw)
        if ts and not out["baslangic"]:
            out["baslangic"] = ts
        if ts:
            out["bitis"] = ts
        s = line.strip()
        if mm := re.match(r"^\[SENKRON\] '(.+)' \((\S+) sarki\)", s):
            current = mm.group(1)
            out["listeler"].append({"ad": current, "sarki": mm.group(2), "durum": ""})
        elif s.startswith("(Degisiklik yok") and out["listeler"]:
            out["listeler"][-1]["durum"] = "değişiklik yok"
        elif s.startswith("[ATLA]"):
            mm = re.match(r"^\[ATLA\] '(.+)'", s)
            out["listeler"].append({"ad": mm.group(1) if mm else s, "sarki": "?", "durum": "atlandı (değişmemiş)"})
        elif s.startswith("+ ") and "(EKLENECEKTI)" not in s:
            out["eklenen"].append((current, re.sub(r"\s+\(skor.*$", "", s[2:])))
        elif s.startswith("? SUPHELI:"):
            out["supheli"].append((current, re.sub(r"\s+\(en iyi skor.*$", "", s[len("? SUPHELI:"):].strip())))
        elif s.startswith("- SILINDI:"):
            out["silinen"].append((current, s[len("- SILINDI:"):].strip()))
        elif s.startswith("[SIRA]"):
            out["sira"].append(s[len("[SIRA]"):].strip())
        elif s.startswith("! ") or "Traceback" in s or s.startswith("Error"):
            out["hatalar"].append(s.lstrip("! ").strip())
        if s.startswith("Bitti."):
            out["bitti"] = True
    return out


def latest_log(durum_dir=None):
    d = Path(durum_dir or DURUM_DIR)
    logs = sorted(d.glob("calisma-*.log"))
    return logs[-1] if logs else None


# --- alt komutlar ------------------------------------------------------------

def cmd_ozet(db=None, durum_dir=None):
    names = playlist_names(durum_dir)
    lines = []
    log = latest_log(durum_dir)
    if log is None:
        lines.append("Son gece senkronunun kaydı yok (kayıt adımı ilk kez bu gece çalışacak olabilir).")
    else:
        run = parse_run(log.read_text(encoding="utf-8", errors="replace"))
        durum = "tamamlandı" if run["bitti"] else "TAMAMLANMADI (yarıda kesildi ya da hata)"
        lines.append(f"Son gece senkronu: {run['baslangic'] or '?'} → {run['bitis'] or '?'}, {durum}.")
        lines.append(f"Taranan liste: {len(run['listeler'])}; eklenen {len(run['eklenen'])}, "
                     f"şüpheli {len(run['supheli'])}, silinen {len(run['silinen'])}, hata {len(run['hatalar'])}.")
        for pl, t in run["eklenen"]:
            lines.append(f"  + {t}  → {pl}")
        for pl, t in run["supheli"]:
            lines.append(f"  ? {t}  → {pl} (inceleme bekliyor)")
        for pl, t in run["silinen"]:
            lines.append(f"  - {t}  ← {pl}")
        moved = [s for s in run["sira"] if "zaten sirali" not in s]
        if moved:
            lines.append("Sıralama: " + "; ".join(moved))
        for e in run["hatalar"][:8]:
            lines.append(f"  ! {e[:220]}")
        if len(run["hatalar"]) > 8:
            lines.append(f"  … +{len(run['hatalar']) - 8} hata satırı ({log})")
    with open_db(db) as conn:
        synced = dict(conn.execute(
            "SELECT yt_playlist_id, COUNT(*) FROM synced_tracks GROUP BY yt_playlist_id").fetchall())
        pending = dict(conn.execute(
            "SELECT yt_playlist_id, COUNT(*) FROM pending_review GROUP BY yt_playlist_id").fetchall())
        last = conn.execute("SELECT MAX(synced_at) FROM synced_tracks").fetchone()[0]
    lines.append(f"Music Sync kaydı: {sum(synced.values())} şarkı YouTube'a geçmiş, "
                 f"{sum(pending.values())} şüpheli eşleşme inceleme bekliyor; son ekleme {last or '?'} (UTC).")
    for yt in sorted(set(synced) | set(pending), key=lambda k: -synced.get(k, 0)):
        p = f", {pending[yt]} bekliyor" if pending.get(yt) else ""
        lines.append(f"  {label(yt, names)}: {synced.get(yt, 0)} geçmiş{p}")
    return "\n".join(lines)


def cmd_ara(query, db=None, durum_dir=None):
    q = norm(query)
    if len(q) < 2:
        raise SystemExit("Aranacak metin en az 2 karakter olmalı.")
    names = playlist_names(durum_dir)
    words = q.split()

    def hit(*fields):
        hay = norm(" ".join(f or "" for f in fields))
        return all(w in hay for w in words)

    with open_db(db) as conn:
        synced = [r for r in conn.execute(
            "SELECT track_name, artist_name, yt_playlist_id, yt_video_id, synced_at FROM synced_tracks")
            if hit(r["track_name"], r["artist_name"])]
        pending = [r for r in conn.execute(
            "SELECT track_name, artist_name, yt_playlist_id, created_at FROM pending_review")
            if hit(r["track_name"], r["artist_name"])]
    if not synced and not pending:
        return (f"\"{query}\" Music Sync kaydında yok. Ya henüz gece senkronu (03:00) çalışmadı, "
                "ya da şarkı takip edilmeyen bir listede. Spotify'da hangi listede olduğuna eklentiyle bakılabilir.")
    lines = []
    for r in synced[:25]:
        lines.append(f"✓ {r['artist_name']} - {r['track_name']} → YouTube'da, {label(r['yt_playlist_id'], names)} "
                     f"({r['synced_at']} UTC, https://music.youtube.com/watch?v={r['yt_video_id']})")
    for r in pending[:25]:
        lines.append(f"? {r['artist_name']} - {r['track_name']} → {label(r['yt_playlist_id'], names)}: "
                     f"YouTube'a GEÇMEDİ, şüpheli eşleşme olarak inceleme bekliyor ({r['created_at']} UTC). "
                     "Onay Music-Sync botunda /review.")
    extra = len(synced) + len(pending) - len(lines)
    if extra > 0:
        lines.append(f"… +{extra} sonuç daha; aramayı daralt.")
    return "\n".join(lines)


def cmd_bekleyen(liste=None, db=None, durum_dir=None):
    names = playlist_names(durum_dir)
    with open_db(db) as conn:
        rows = conn.execute(
            "SELECT track_name, artist_name, yt_playlist_id, created_at FROM pending_review ORDER BY created_at").fetchall()
    if liste:
        want = norm(liste)
        rows = [r for r in rows if want in norm(label(r["yt_playlist_id"], names))]
    if not rows:
        return "İnceleme bekleyen şüpheli eşleşme yok." + (f" (liste: {liste})" if liste else "")
    lines = [f"{len(rows)} şüpheli eşleşme inceleme bekliyor (YouTube'a geçmediler; onay Music-Sync botunda /review):"]
    for r in rows:
        lines.append(f"  ? {r['artist_name']} - {r['track_name']} → {label(r['yt_playlist_id'], names)} ({r['created_at'][:10]})")
    return "\n".join(lines)


# --- kaydet (yalniz root, ExecStopPost) --------------------------------------

def fetch_name(spotify_id, timeout=6):
    url = ("https://open.spotify.com/oembed?url=https://open.spotify.com/playlist/" + spotify_id)
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode())["title"]


def cmd_kaydet(invocation_id, db=None, durum_dir=None, journal=None, fetch=fetch_name):
    d = Path(durum_dir or DURUM_DIR)
    d.mkdir(mode=0o755, parents=True, exist_ok=True)
    if journal is None:
        journal = subprocess.run(
            ["journalctl", f"_SYSTEMD_INVOCATION_ID={invocation_id}", "--no-pager", "-o", "short-iso"],
            capture_output=True, text=True, timeout=60).stdout
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M")
    log = d / f"calisma-{stamp}.log"
    tmp = log.with_suffix(".tmp")
    tmp.write_text(journal, encoding="utf-8")
    tmp.chmod(0o644)
    tmp.replace(log)
    for old in sorted(d.glob("calisma-*.log"))[:-LOG_KEEP]:
        old.unlink()

    # Liste adlari: ag yoksa eski adi koru.
    f = d / "listeler.json"
    try:
        old = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        old = {}
    with open_db(db) as conn:
        pairs = conn.execute("SELECT spotify_playlist_id, yt_playlist_id FROM playlist_snapshots").fetchall()
    new = {}
    for sp, yt in pairs:
        ad = (old.get(sp) or {}).get("ad")
        try:
            ad = fetch(sp)
        except Exception:
            pass
        new[sp] = {"ad": ad, "yt": yt}
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(new, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.chmod(0o644)
    tmp.replace(f)
    return f"kaydedildi: {log.name}, {len(new)} liste adı"


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print((__doc__ or "").strip())
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd == "ozet":
        print(cmd_ozet())
    elif cmd == "ara" and rest:
        print(cmd_ara(" ".join(rest)))
    elif cmd == "bekleyen":
        print(cmd_bekleyen(" ".join(rest) or None))
    elif cmd == "kaydet" and rest:
        print(cmd_kaydet(rest[0]))
    else:
        print((__doc__ or "").strip(), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
