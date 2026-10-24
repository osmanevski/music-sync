"""Ozan'in Telegram cikisi: Music-Sync botu uzerinden (Hermes Telegram botu DEGIL).

Ozan (hermes kullanicisi) mesaji giden kutusuna birakir; Music-Sync botu (root, token sahibi)
kutuyu birkac saniyede bir bosaltip Osman'a gonderir.

    python3 -m dinleme.telegram_giden "Ozan: mesaj"
    python3 -m dinleme.telegram_giden -f rapor.txt
"""
import json
import os
import sys
import time
import uuid

DATA = os.environ.get("OZAN_DATA", "/var/lib/hermes/profiles/ozan/data")
OUTBOX = os.path.join(DATA, "giden")
MAX_LEN = 3800


def put(text, outbox=OUTBOX):
    text = (text or "").strip()
    if not text:
        raise ValueError("bos mesaj")
    if not text.startswith("Ozan"):
        text = "Ozan: " + text
    os.makedirs(outbox, mode=0o700, exist_ok=True)
    name = f"{time.time():.6f}-{uuid.uuid4().hex[:8]}.json"
    tmp = os.path.join(outbox, "." + name)
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"text": text, "at": time.time()}, f, ensure_ascii=False)
    os.chmod(tmp, 0o600)
    os.replace(tmp, os.path.join(outbox, name))
    return name


def take(outbox=OUTBOX):
    """Kutudaki mesajlari siraya gore dondurur ve siler (root/bot tarafi)."""
    try:
        names = sorted(n for n in os.listdir(outbox) if n.endswith(".json") and not n.startswith("."))
    except FileNotFoundError:
        return []
    out = []
    for n in names:
        p = os.path.join(outbox, n)
        try:
            with open(p, encoding="utf-8") as f:
                text = str(json.load(f).get("text") or "").strip()
        except (OSError, ValueError):
            text = ""
        try:
            os.remove(p)
        except OSError:
            pass
        if text:
            out.append(text)
    return out


def chunks(text, size=MAX_LEN):
    text = text.strip()
    while len(text) > size:
        cut = text.rfind("\n", 0, size)
        cut = cut if cut > size // 2 else size
        yield text[:cut]
        text = text[cut:].lstrip("\n")
    if text:
        yield text


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    if argv[0] == "-f":
        with open(argv[1], encoding="utf-8") as f:
            text = f.read()
    else:
        text = " ".join(argv)
    put(text)
    print("kuyrukta: Music-Sync botu birkac saniye icinde gonderecek")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
