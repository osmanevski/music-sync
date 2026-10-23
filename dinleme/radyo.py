"""Ozan'in Osmanevski.com radyo yonetimi (yalniz /mesaj/panel/radio).

Mesaj servisi sunucuda 127.0.0.1:8660'ta dinler; panel kimligi Caddy'dedir, yerel cagri
X-Mesaj-Panel basligiyla dogrudan girer. Bu arac bilerek yalniz radyo ucunu kullanir:
ziyaretci mesajlari, istatistik ve diger panel uclari Ozan'in isi degildir.

    python -m dinleme.radyo durum [--sira N]
    python -m dinleme.radyo islem <action> [anahtar=deger ...]
      ornek: islem next | islem add url=https://www.youtube.com/watch?v=... |
             islem move id=XXX before=YYY | islem refresh url=https://www.youtube.com/playlist?list=...
Sira degistiren islemlere guncel `revision` otomatik eklenir.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get("OZAN_RADYO_URL", "http://127.0.0.1:8660/mesaj/panel/radio")
REVISION_ACTIONS = {"move", "remove", "play", "seek", "next", "block", "repeat", "shuffle",
                    "enqueue", "play_saved", "append_playlist"}
ACTIONS = {"refresh", "add", "enable", "disable", "pause", "resume", "next", "block", "unblock",
           "move", "remove", "play", "seek", "repeat", "shuffle", "favorite", "save_playlist",
           "delete_playlist", "append_playlist", "enqueue", "play_saved"}


def request(method, body=None, opener=urllib.request.urlopen):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE, data=data, method=method, headers={
        "X-Mesaj-Panel": "1", "Content-Type": "application/json"})
    try:
        with opener(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode()).get("hata")
        except Exception:
            msg = None
        raise RuntimeError(f"radyo {e.code}: {msg or e.reason}") from None


def parse_value(raw):
    if raw in ("true", "false"):
        return raw == "true"
    if raw == "null":
        return None
    try:
        return float(raw) if "." in raw else int(raw)
    except ValueError:
        return raw


def build_action(action, pairs, state_fn):
    if action not in ACTIONS:
        raise ValueError(f"bilinmeyen islem: {action}")
    body = {"action": action}
    for p in pairs:
        if "=" not in p:
            raise ValueError(f"anahtar=deger bekleniyor: {p}")
        k, v = p.split("=", 1)
        body[k] = v if k in ("url", "name", "id", "before") and v != "null" else parse_value(v)
    if action in REVISION_ACTIONS and "revision" not in body:
        body["revision"] = state_fn()["revision"]
    return body


def fmt(t):
    if not t:
        return "-"
    return f"{t.get('artist') or '?'} - {t.get('title') or '?'} [{t.get('id')}]"


def summary(s, n=10):
    lines = [f"yayin: {'acik' if s.get('enabled') else 'kapali'}{' (duraklatildi)' if s.get('paused') else ''}"
             f"{' (dongu)' if s.get('repeat') else ''}",
             f"liste: {s.get('title')} ({s.get('count')} parca, {s.get('blocked')} cikarilmis) {s.get('url')}"]
    tr = s.get("track")
    if tr:
        lines.append(f"calan: {fmt(tr)} {int(s.get('position') or 0)}/{tr.get('duration')} sn")
    lines.append(f"sira (ilk {n}):")
    lines += [f"  {i + 1}. {fmt(t)}" for i, t in enumerate((s.get("queue") or [])[:n])]
    pls = s.get("playlists") or []
    lines.append("kayitli listeler: " + (", ".join(f"{p['name']} [{p['id']}]" for p in pls) or "yok"))
    lines.append(f"favoriler: {len(s.get('favorites') or [])}  revision: {s.get('revision')}")
    job = s.get("job") or {}
    if job.get("running") or job.get("error"):
        lines.append(f"yenileme: {'suruyor' if job.get('running') else 'hata: ' + str(job.get('error'))}")
    return "\n".join(lines)


def main(argv):
    if not argv or argv[0] not in ("durum", "islem", "json"):
        print(__doc__)
        return 2
    if argv[0] == "json":
        print(json.dumps(request("GET"), ensure_ascii=False, indent=1))
        return 0
    if argv[0] == "durum":
        n = int(argv[argv.index("--sira") + 1]) if "--sira" in argv else 10
        print(summary(request("GET"), n))
        return 0
    if len(argv) < 2:
        print("islem adi gerekli")
        return 2
    body = build_action(argv[1], argv[2:], lambda: request("GET"))
    s = request("PUT", body)
    if argv[1] in ("refresh", "add"):
        time.sleep(1)
    print("tamam: " + json.dumps({k: v for k, v in body.items() if k != "revision"}, ensure_ascii=False))
    print(summary(s, 5))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except (RuntimeError, ValueError) as e:
        print(f"HATA: {e}")
        sys.exit(1)
