#!/usr/bin/env python3
"""Ozan rutini (Hermes cron, no_agent): saatlik dinleme toplama.

Kurulum yeri: /var/lib/hermes/profiles/ozan/scripts/ozan-topla.py (kaynak: music-sync/dinleme/).
stdout bos = sessiz tur. Ariza esigi asilirsa uyari hem yazdirilir hem Music-Sync Telegram
botunun giden kutusuna birakilir (Hermes Telegram botu kullanilmaz).
"""
import json
import os
import sys

MUSIC_SYNC = "/opt/music-sync"
HERMES_AGENT = "/usr/local/lib/hermes-agent"
MAIN_HOME = "/var/lib/hermes"          # Spotify girisi ana profilde
DATA = "/var/lib/hermes/profiles/ozan/data"

sys.path.insert(0, MUSIC_SYNC)
from dinleme import calistir, siniflandir, telegram_giden  # noqa: E402


def spotify_fetch():
    os.environ["HERMES_HOME"] = MAIN_HOME  # tek token sahibi: ana profil (kilitli yenileme)
    for p in (HERMES_AGENT, os.path.join(MAIN_HOME, "plugins")):
        if p not in sys.path:
            sys.path.insert(0, p)
    from spotify.spotify_client import SpotifyClient
    data = SpotifyClient().request("GET", "/me/player/recently-played", params={"limit": 50})
    return (data or {}).get("items", [])


def telegram(text):
    try:
        telegram_giden.put(text)
    except Exception:
        pass


def main():
    summary, alerts = calistir.run(os.path.join(DATA, "dinleme.db"), os.path.join(DATA, "yt-gecmis.json"),
                                   spotify_fetch, siniflandir.classify)
    with open(os.path.join(DATA, "son-tur.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, default=str)
    if alerts:
        text = "\n".join(alerts)
        telegram(text)
        print(text)


if __name__ == "__main__":
    main()
