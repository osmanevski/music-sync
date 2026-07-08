"""
Telegram bildirim gonderici.
config'te TELEGRAM_TOKEN ve TELEGRAM_CHAT_ID doluysa mesaj gonderir.
Bos ise sessizce hicbir sey yapmaz (program calismaya devam eder).
"""
import ssl
import urllib.request
import urllib.parse
import config


def send(message):
    """Telegram'a mesaj gonder. Basarisiz olursa programi COKERTME, sadece uyar."""
    token = config.TELEGRAM_TOKEN
    chat_id = config.TELEGRAM_CHAT_ID
    if not token or not chat_id:
        return  # bildirim ayarlanmamis, sessizce gec

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode("utf-8")

    # Bazi sunucu aglarinda (kurumsal guvenlik duvari/antivirus) HTTPS araya
    # girip kendi sertifikasiyla imzaliyor; Python buna guvenmiyor.
    # Bildirim hassas veri tasimadigi icin bu istek icin dogrulamayi esnetiyoruz.
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    try:
        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            resp.read()
    except Exception as e:
        # Bildirim gonderilemese bile senkron basarili sayilir
        print(f"  ! Telegram bildirimi gonderilemedi: {e}")
