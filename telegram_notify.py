"""
Telegram bildirim gonderici.
config'te TELEGRAM_TOKEN ve TELEGRAM_CHAT_ID doluysa mesaj gonderir.
Bos ise sessizce hicbir sey yapmaz (program calismaya devam eder).
"""
import ssl
import urllib.request
import urllib.parse
import certifi
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

    # SSL dogrulamasi ACIK. Windows sistem deposu bu sunucuda bozuk/self-signed
    # bir kok yuzunden zinciri kuramiyordu; certifi'nin CA paketini kullaniyoruz.
    # Boylece hostname + sertifika zinciri dogrulanir (MITM'e karsi korumali).
    # (Not: URL'de bot token gidiyor, bu yuzden dogrulama sart.)
    ctx = ssl.create_default_context(cafile=certifi.where())

    try:
        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            resp.read()
    except Exception as e:
        # Bildirim gonderilemese bile senkron basarili sayilir
        print(f"  ! Telegram bildirimi gonderilemedi: {e}")
