"""YouTube izleme gecmisini ceker ve cerezsiz bir JSON'a yazar (root olarak calisir).

browser.json'daki Google cerezleri yalniz root'ta kalir; Ozan'in toplayicisi (hermes kullanicisi)
sadece bu dosyadaki video id + basliklari okur.

    python -m dinleme.yt_gecmis            # YTGECMIS_OUT'a yazar
Ortam: YTGECMIS_OUT, YTGECMIS_LIMIT (200), YTGECMIS_YTDLP, YTGECMIS_OWNER (hermes)
"""
import datetime as dt
import json
import os
import pwd
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BROWSER = os.path.join(ROOT, "browser.json")
YTDLP = os.environ.get("YTGECMIS_YTDLP", "/opt/osmanevski-mesaj/venv/bin/yt-dlp")
OUT = os.environ.get("YTGECMIS_OUT", "/var/lib/hermes/profiles/ozan/data/yt-gecmis.json")
LIMIT = int(os.environ.get("YTGECMIS_LIMIT", "200"))
OWNER = os.environ.get("YTGECMIS_OWNER", "hermes")
AUTH_HINTS = ("sign in", "login", "cookies", "consent", "401", "403")


def write_cookie_file(browser_path):
    with open(browser_path, encoding="utf-8") as f:
        headers = json.load(f)
    cookie = next((v for k, v in headers.items() if k.lower() == "cookie"), None)
    if not cookie:
        raise RuntimeError("browser.json icinde Cookie basligi yok")
    exp = int(time.time()) + 3600
    fd, path = tempfile.mkstemp(prefix=".ytc-")
    with os.fdopen(fd, "w") as f:
        f.write("# Netscape HTTP Cookie File\n")
        for part in cookie.split(";"):
            if "=" in part:
                name, value = part.strip().split("=", 1)
                f.write(f".youtube.com\tTRUE\t/\tTRUE\t{exp}\t{name}\t{value}\n")
    return path


def parse_lines(text):
    items = []
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) < 2 or not parts[0].strip():
            continue
        dur = parts[2].strip() if len(parts) > 2 else ""
        try:
            duration = float(dur)
        except ValueError:
            duration = None
        items.append({"id": parts[0].strip(), "title": parts[1].strip(), "duration": duration})
    return items


def fetch():
    cookie_path = write_cookie_file(BROWSER)
    try:
        r = subprocess.run(
            [YTDLP, "--ignore-config", "--cookies", cookie_path, "--flat-playlist",
             "--playlist-end", str(LIMIT), "--print", "%(id)s\t%(title)s\t%(duration)s", ":ythistory"],
            capture_output=True, text=True, timeout=240)
    finally:
        os.remove(cookie_path)
    items = parse_lines(r.stdout)
    if items:
        return {"ok": True, "error": None, "items": items}
    err = (r.stderr or "").strip().splitlines()[-1:] or ["bos cikti"]
    auth = any(h in r.stderr.lower() for h in AUTH_HINTS)
    return {"ok": False, "auth_error": auth, "error": err[0][:300], "items": []}


def write_atomic(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".yt-gecmis-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.chmod(tmp, 0o600)
    if os.geteuid() == 0:
        pw = pwd.getpwnam(OWNER)
        os.chown(tmp, pw.pw_uid, pw.pw_gid)
    os.replace(tmp, path)


def main():
    try:
        data = fetch()
    except Exception as e:  # browser.json eksik, yt-dlp yok, zaman asimi
        data = {"ok": False, "auth_error": False, "error": f"{type(e).__name__}: {e}"[:300], "items": []}
    data["fetched_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    write_atomic(OUT, data)
    print(f"yt-gecmis: ok={data['ok']} oge={len(data['items'])}" + (f" hata={data['error']}" if not data["ok"] else ""))
    return 0 if data["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
