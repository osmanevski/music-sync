# Spotify ↔ YouTube Music Sync

Spotify ve YouTube Music çalma listelerini iki yönde senkronize eden, fark-bazlı çalışan bir araç. Şarkı adı + sanatçı + süre ile eşleştirir. Telegram botu ile butonlu yönetim ve zamanlanmış otomatik senkron destekler.

## Özellikler

- **Fark-bazlı senkron:** Spotify listesinin önceki hâli ile güncel hâlini karşılaştırır; yalnızca yeni eklenen şarkıları YouTube'a ekler, çıkarılanları siler.
- **Müzik/video ayrımı:** YouTube Music aramalarında gerçek müzik kayıtlarını (Topic kanalları / song sonuçları) tercih eder, video versiyonlarını cezalandırır.
- **Güvenli silme:** Yalnızca programın eklediği şarkılar silinir; elle eklediklerin korunur.
- **İlk dolum (`--import`):** Mevcut bir listeyi YouTube'a aktarır, zaten var olanları atlar.
- **Şüpheli eşleşme incelemesi:** Düşük skorlu eşleşmeler kuyruğa alınır, elle/Telegram üzerinden onaylanır.
- **Mükerrer temizliği:** Aynı isim+sanatçıya sahip tekrar eden şarkıları bulur ve temizler.
- **Telegram botu:** Butonlu arayüzle senkron, import, mükerrer kontrol, şüpheli inceleme.
- **YouTube → Spotify:** YouTube Music listesini aynı adlı Spotify listesine aktarır; mevcut şarkıları korur ve yalnızca aracın eklediği şarkıları siler.

## Kurulum

```bash
git clone <repo-url>
cd ytmusic-sync
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate
pip install -r requirements.txt
```

### Yapılandırma

1. `.env.example` dosyasını `.env` olarak kopyalayıp doldurun:
   - **Spotify:** https://developer.spotify.com/dashboard adresinden bir uygulama oluşturun, Redirect URI olarak `http://127.0.0.1:8888/callback` ekleyin.
   - **YouTube Music:** browser authentication kullanılır (aşağıya bakın).
   - **Telegram (opsiyonel):** @BotFather'dan bir bot oluşturup token alın; chat ID'nizi `getUpdates` ile öğrenin.

2. `watchlist.example.txt` dosyasını `watchlist.txt` olarak kopyalayıp takip etmek istediğiniz Spotify liste ID'lerini ekleyin. ID'leri görmek için: `python sync.py --list`

3. YouTube Music browser auth:
   - Tarayıcıda music.youtube.com'a girin (oturum açık olmalı).
   - Geliştirici araçları → Network → `youtubei` filtreleyin → bir `browse` isteğine sağ tık → "Copy as cURL".
   - Çıktıyı `headers.txt` dosyasına yapıştırın.
   - `python setup_yt_browser.py headers.txt` çalıştırın → `browser.json` oluşur.

## Kullanım

```bash
python sync.py --list                      # Spotify listelerini ve ID'lerini göster
python sync.py                             # watchlist'teki listeleri senkronla
python sync.py --playlist <id>            # tek liste
python sync.py --all                       # tüm listeler
python sync.py --dry-run                   # önizleme (hiçbir şey yapmaz)
python sync.py --playlist <id> --import    # ilk dolum (tüm şarkıları aktar)
python reverse_sync.py --list              # YouTube Music listelerini göster
python reverse_sync.py --playlist <id>     # YouTube Music'ten Spotify'a senkronla
python reverse_sync.py --playlist <id> --dry-run  # ters yön önizleme
python review.py [spotify_id]              # şüpheli eşleşmeleri incele
python find_duplicates.py <id|isim>        # YouTube'da mükerrer bul
python clean_duplicates.py <id|isim>       # YouTube'da mükerrer temizle
python bot.py                              # Telegram botunu başlat
```

## Telegram Bot Kurulumu (opsiyonel)

Bot, senkronu Telegram'dan butonlarla yönetmenizi ve bildirim almanızı sağlar.

### 1. Bot oluşturma
1. Telegram'da [@BotFather](https://t.me/BotFather)'a yazın.
2. `/newbot` gönderin, bota bir ad ve kullanıcı adı verin.
3. BotFather bir **token** verir (örn. `123456789:ABCdef...`). Bunu `.env`'deki `TELEGRAM_TOKEN`'a yazın.

### 2. Chat ID öğrenme
1. Oluşturduğunuz bota Telegram'da herhangi bir mesaj gönderin (örn. "merhaba").
2. Tarayıcıda şu adrese gidin (TOKEN yerine kendi token'ınız):
   `https://api.telegram.org/bot<TOKEN>/getUpdates`
3. Çıkan JSON'da `"chat":{"id":123456789...` kısmındaki sayı sizin chat ID'nizdir.
4. Bu sayıyı `.env`'deki `TELEGRAM_CHAT_ID`'ye yazın.

> Bot yalnızca bu chat ID'den gelen komutları işler (güvenlik). Başkaları botu kullanamaz.

### 3. Botu çalıştırma
```bash
python bot.py
```
Telegram'da `/menu` yazın; butonlu arayüz açılır. Bot sürekli açık kalmalıdır (sunucuda Görev Zamanlayıcı ile otomatik başlatılabilir — bkz. WINDOWS_KURULUM.md).

**Komutlar:** `/menu`, `/sync`, `/sync <liste adı>`, `/ytsync <liste adı>`, `/list`, `/review`

## Otomatik çalışma (Windows)

`run_sync.bat` (günlük senkron) ve `run_bot.bat` (Telegram botu) dosyalarını Görev Zamanlayıcı ile çalıştırın. Detaylar için [WINDOWS_KURULUM.md](WINDOWS_KURULUM.md).

> **Not:** `.bat` dosyalarındaki `C:\ytmusic-sync` yolunu kendi kurulum dizininize göre düzenleyin.

## Sık Karşılaşılan Sorunlar

**YouTube auth: cURL'de cookie yok**
Chrome cookie'yi `-b` bayrağında verir; `setup_yt_browser.py` bunu yakalar. Opera bazı sürümlerde cookie'yi cURL'e hiç eklemez — bu durumda Chrome kullanın. cURL'de cookie olup olmadığını `grep -c cookie headers.txt` (Windows: `findstr /c:"-b " headers.txt`) ile kontrol edebilirsiniz.

**Windows'ta Türkçe/özel karakter hatası (`UnicodeEncodeError` / `charmap`)**
Konsolun kod sayfası UTF-8 değilse Türkçe liste isimleri çökmeye yol açar. `.bat` dosyaları `chcp 65001` ve `PYTHONUTF8=1` ile bunu çözer; elle çalıştırırken `set PYTHONUTF8=1` yapabilirsiniz.

**`ytmusicapi` OAuth `expires_in` / HTTP 400 hatası**
OAuth yöntemi YouTube Music'in dahili API'siyle sorun çıkarabiliyor. Bu araç bu yüzden **browser authentication** kullanır (`setup_yt_browser.py`). OAuth'u denemeyin.

**Kurumsal ağ / SSL sertifika hatası (`CERTIFICATE_VERIFY_FAILED`)**
Telegram bağlantıları sertifikayı `certifi` CA paketiyle doğrular. Sorun sürerse ağ/DNS ayarlarını kontrol edin; sertifika doğrulamasını kapatmayın.

**"Liste ilk kez görülüyor, ekleme yapılmadı"**
Fark-bazlı çalışma gereği: ilk görülen liste referans olarak kaydedilir, şarkılar eklenmez. Mevcut bir listenin tüm şarkılarını aktarmak için `--import` kullanın.

**Boş YouTube listesinde `'contents'` hatası**
`ytmusicapi`, tamamen boş bir listeyi okurken hata verebilir. Araç bunu yakalar ve "liste boş" diyerek geçer; bir şey yapmanız gerekmez.

## Güvenlik

`.env`, `browser.json`, `sync.db`, `watchlist.txt` gibi kişisel/gizli dosyalar `.gitignore` ile hariç tutulmuştur. **Bu dosyaları asla depoya yüklemeyin** — API anahtarları ve oturum bilgileri içerirler.

## Teknik notlar

YouTube Music entegrasyonu resmi olmayan [ytmusicapi](https://github.com/sigma67/ytmusicapi) kütüphanesini kullanır. YouTube arayüz değişikliklerinde kütüphanenin güncellenmesi gerekebilir. Bu araç kişisel kullanım içindir.

## Lisans

MIT
