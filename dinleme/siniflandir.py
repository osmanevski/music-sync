"""YouTube videolarini 'muzik mi' diye Haiku 5.5 ile siniflandirir (Claude Code CLI uzerinden).

Model kurali: yalniz Claude 5.5 ailesi; bu is icin Haiku 5.5.
"""
import json
import os
import re
import subprocess

MODEL = "claude-haiku-5-5"
CLAUDE = os.environ.get("OZAN_CLAUDE", "/usr/local/bin/claude")
CLAUDE_ENV = os.environ.get("OZAN_CLAUDE_ENV", "/etc/hermes/claude.env")

PROMPT = """Asagida Osman'in YouTube izleme gecmisinden videolar var (id | baslik | sure sn).
Her biri icin karar ver: bu video MUZIK DINLEMEK icin izlenmis bir sarki/performans mi?

EVET: resmi klip, canli performans, TRT arsiv kaydi, konser, albüm/ses kaydi, yarisma ya da
eglence programinda (Sen Turkulerini Soyle, Yetenek Sizsiniz vb.) tek bir sarkinin seslendirildigi kesit.
HAYIR: mac/spor, teknoloji, haber, siyaset, tartisma, belgesel, ses analizi/roportaj, tam bolum
(birden cok konuk ve sohbet), ders, vlog.

Muzikse:
- "sanatcilar": seslendiren(ler), Turkce dogru yazimla ve normal buyuk/kucuk harfle
  (ornek: "AYSUN GÜLTEKİN" -> "Aysun Gültekin", "Gulsen Kutlu" -> "Gülşen Kutlu"). Yalniz kisi/grup adi.
- "eser": sarkinin adi, ayni sekilde duzeltilmis; bolum numarasi, kanal adi, yil, "Official" vb. olmadan.

YALNIZ bir JSON dizi dondur, baska metin yok:
[{"id": "...", "muzik": true, "sanatcilar": ["..."], "eser": "..."}, {"id": "...", "muzik": false}]

Videolar:
"""


def load_env(path=CLAUDE_ENV):
    env = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return env


def build_prompt(videos):
    rows = []
    for vid, title, duration in videos:
        d = f"{int(duration)}" if duration else "?"
        rows.append(f"{vid} | {title} | {d}")
    return PROMPT + "\n".join(rows)


def parse_reply(text):
    text = text.strip()
    m = re.search(r"\[.*\]", text, re.S)
    if not m:
        raise ValueError("cevapta JSON dizi yok")
    data = json.loads(m.group(0))
    if not isinstance(data, list):
        raise ValueError("JSON dizi degil")
    return [d for d in data if isinstance(d, dict)]


def classify(videos, run=subprocess.run, timeout=240):
    """videos: [(id, title, duration)] -> [{"id","muzik","sanatcilar","eser"}]"""
    if not videos:
        return []
    env = dict(os.environ)
    env.update(load_env())
    r = run([CLAUDE, "-p", build_prompt(videos), "--model", MODEL, "--output-format", "json",
             "--max-turns", "1", "--tools", ""],
            capture_output=True, text=True, timeout=timeout, env=env)
    if r.returncode != 0:
        raise RuntimeError(f"claude cikis {r.returncode}: {(r.stderr or r.stdout)[-300:]}")
    payload = json.loads(r.stdout)
    if payload.get("is_error"):
        raise RuntimeError(f"claude hata: {str(payload.get('result'))[:300]}")
    return parse_reply(payload.get("result") or "")
