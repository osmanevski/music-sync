"""
YouTube Music icin OAuth token'i bir kereligine olusturur.
oauth.json dosyasi olusturur; sonra sync.py bunu kullanir.

Kullanim: python setup_yt_auth.py
Terminalde bir link ve kod cikar, tarayicida acip onaylayacaksin.
"""
from ytmusicapi import setup_oauth
import config

config.validate()
print("YouTube Music OAuth kurulumu basliyor...")
print("Terminaldeki yonergeleri takip et (link + kod).\n")

setup_oauth(
    client_id=config.YT_CLIENT_ID,
    client_secret=config.YT_CLIENT_SECRET,
    filepath=config.YT_OAUTH_FILE,
    open_browser=True,
)
print(f"\nTamam. '{config.YT_OAUTH_FILE}' olusturuldu.")
