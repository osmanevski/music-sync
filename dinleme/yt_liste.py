"""Ozan'in akis istegini YouTube'a yazar (root; browser.json burada kalir).

systemd .path, `akis-istek.json` degisince bunu calistirir. Liste UNLISTED olusturulur
(radyonun cerezsiz yt-dlp'si okuyabilsin) ve her istekte icerigi istekteki sirayla degistirilir.
Yalniz kendi olusturdugu listeye (durum dosyasindaki id) dokunur; Music Sync listelerine asla.
"""
import json
import os
import pwd
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.environ.get("OZAN_DATA", "/var/lib/hermes/profiles/ozan/data")
REQUEST = os.path.join(DATA, "akis-istek.json")
RESULT = os.path.join(DATA, "akis-sonuc.json")
STATE = os.path.join(ROOT, "akis-state.json")   # root: Ozan'in liste id'si
OWNER = os.environ.get("YTGECMIS_OWNER", "hermes")
MAX_IDS = 200
VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


def load(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save(path, data, owner=None):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.chmod(tmp, 0o600)
    if owner and os.geteuid() == 0:
        pw = pwd.getpwnam(owner)
        os.chown(tmp, pw.pw_uid, pw.pw_gid)
    os.replace(tmp, path)


def validate(req):
    ids = req.get("video_ids") if isinstance(req, dict) else None
    if not isinstance(ids, list) or not ids:
        raise ValueError("video_ids bos")
    clean, seen = [], set()
    for v in ids[:MAX_IDS]:
        if isinstance(v, str) and VIDEO_ID.match(v) and v not in seen:
            clean.append(v)
            seen.add(v)
    if not clean:
        raise ValueError("gecerli video id yok")
    title = str(req.get("title") or "Ozan · Akış")[:150]
    return title, clean


def replace_playlist(yt, state, title, ids):
    pid = state.get("playlist_id")
    pl = {"tracks": []}
    if pid:
        # Okuma hatasi (ag/DNS) yeni liste acmaya donusmesin: yalniz liste gercekten yoksa olustur.
        try:
            pl = yt.get_playlist(pid, limit=None)
        except Exception as e:
            if "404" not in str(e) and "not found" not in str(e).lower():
                raise
            pid = None
    if not pid:
        pid = yt.create_playlist(title, "Ozan (DJ) — Osman'ın son dinlediklerinden haftalık akış.",
                                 privacy_status="UNLISTED")
        if not isinstance(pid, str):
            raise RuntimeError(f"liste olusturulamadi: {pid}")
        pl = {"tracks": []}
    old = [t for t in pl.get("tracks") or [] if t.get("setVideoId")]
    if old:
        yt.remove_playlist_items(pid, old)
    if pl.get("title") and pl.get("title") != title:
        yt.edit_playlist(pid, title=title)
    resp = yt.add_playlist_items(pid, ids, duplicates=False)
    status = resp if isinstance(resp, str) else (resp or {}).get("status", "")
    if "SUCCEEDED" not in str(status):
        raise RuntimeError(f"ekleme basarisiz: {str(resp)[:200]}")
    got = [t.get("videoId") for t in (yt.get_playlist(pid, limit=None).get("tracks") or [])]
    # YouTube Music, resmi klipleri listede "sarki" karsiligiyla (farkli videoId) gosterebilir;
    # sayi tutuyorsa eksik yok demektir.
    if len(got) >= len(ids):
        return pid, list(ids), []
    return pid, [v for v in ids if v in got], [v for v in ids if v not in got]


def main():
    req = load(REQUEST)
    if req is None:
        return 0
    result = {"request_at": req.get("at", time.time()), "finished": time.time()}
    try:
        title, ids = validate(req)
        sys.path.insert(0, ROOT)
        os.chdir(ROOT)
        import ytmusic_client
        state = load(STATE, {})
        pid, added, missing = replace_playlist(ytmusic_client.get_client(), state, title, ids)
        save(STATE, {"playlist_id": pid, "title": title, "updated": time.time()})
        result.update(ok=True, title=title, playlist_id=pid, added=len(added), missing=missing,
                      url=f"https://www.youtube.com/playlist?list={pid}")
    except Exception as e:
        result.update(ok=False, error=f"{type(e).__name__}: {e}"[:400])
    result["finished"] = time.time()
    save(RESULT, result, owner=OWNER)
    try:
        os.remove(REQUEST)
    except OSError:
        pass
    print(json.dumps({k: v for k, v in result.items() if k != "missing"}, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
