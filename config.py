"""
Tum ayarlar burada. Eslestirme toleranslari, dosya yollari vs.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# --- Spotify ---
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback")
SPOTIFY_SCOPE = (
    "playlist-read-private playlist-read-collaborative "
    "playlist-modify-private playlist-modify-public"
)

# --- YouTube Music ---
YT_CLIENT_ID = os.getenv("YT_CLIENT_ID")
YT_CLIENT_SECRET = os.getenv("YT_CLIENT_SECRET")
YT_OAUTH_FILE = "oauth.json"
YT_BROWSER_FILE = "browser.json"

# --- Eslestirme ayarlari ---
# Sarki suresi karsilastirmasi icin tolerans (saniye).
# Spotify ile YouTube ayni sarkida bazen intro/outro farki olabiliyor.
DURATION_TOLERANCE_SEC = 4

# Bir eslesmeyi "kesin" saymak icin minimum skor (0-100).
# Bunun altindakiler "supheli" olarak isaretlenir, otomatik eklenmez.
MIN_CONFIDENCE_SCORE = 75

# YouTube Music aramasinda kac sonuca bakilacak (en iyiyi secmek icin)
SEARCH_RESULT_LIMIT = 5

# --- Veritabani ---
DB_PATH = "sync.db"

# --- Telegram bildirim (opsiyonel) ---
# .env'e TELEGRAM_TOKEN ve TELEGRAM_CHAT_ID koyarsan bildirim gonderilir.
# Bos birakirsan bildirim gonderilmez (program yine calisir).
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


def validate():
    """Eksik ayar var mi kontrol et, varsa anlasilir hata ver."""
    missing = []
    for name in ["SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET",
                 "YT_CLIENT_ID", "YT_CLIENT_SECRET"]:
        if not globals().get(name):
            missing.append(name)
    if missing:
        raise SystemExit(
            "Eksik ayarlar: " + ", ".join(missing) +
            "\n.env dosyasini .env.example'a gore doldurdugundan emin ol."
        )
