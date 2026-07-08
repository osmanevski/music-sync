# Windows Sunucuda Otomatik Çalışma Kurulumu

Bu rehber, projeyi Windows sunucuda kurup iki şeyi otomatikleştirir:
1. **Günlük senkron** — Spotify'daki değişiklikleri YouTube Music'e yansıtır (Görev Zamanlayıcı, günde bir).
2. **Telegram botu** — sürekli açık kalır, sunucu her açıldığında otomatik başlar.

## 1. Projeyi ve gizli dosyaları yerleştir

Proje klasörünü `C:\ytmusic-sync` altına koy. Şu gizli dosyaların da olması gerekir (repoda yoktur, ayrıca oluşturulur/taşınır):
- `.env` — API anahtarları (`.env.example`'ı kopyalayıp doldur)
- `browser.json` — YouTube oturumu (`setup_yt_browser.py` ile oluştur)
- `sync.db` — senkron geçmişi (ilk çalıştırmada otomatik oluşur)
- `watchlist.txt` — takip edilen listeler (`watchlist.example.txt`'ten kopyala)

## 2. Python ve kütüphaneler

Python 3.11+ kurulu olmalı. Kurulumda **"Add Python to PATH"** işaretlenmeli.
Alternatif: `winget install Python.Python.3.13 --source winget`

```
cd C:\ytmusic-sync
py -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

## 3. Elle test et

```
python sync.py --list      # listeler geliyorsa bağlantı tamam
python sync.py --dry-run   # önizleme, hiçbir şey yapmaz
```

## 4. .bat dosyalarındaki yolu kontrol et

`run_sync.bat` ve `run_bot.bat` içindeki `cd /d C:\ytmusic-sync` satırı kendi klasör yolunla eşleşmeli. Farklı bir dizine kurduysan düzelt.

## 5. GÖREV 1 — Günlük senkron

1. Başlat menüsünde "Görev Zamanlayıcı" (Task Scheduler) aç.
2. Sağdan **"Temel Görev Oluştur"** (Create Basic Task).
3. Ad: `YTMusic Sync` → İleri.
4. Tetikleyici: **"Günlük"** (Daily) → İleri → başlangıç saatini seç (örn. gece 03:00) → İleri.
5. Eylem: **"Program başlat"** (Start a program) → İleri.
6. Program/komut dosyası: `C:\ytmusic-sync\run_sync.bat`
7. Başlangıç konumu (Start in): `C:\ytmusic-sync`
8. İleri → Son.
9. Göreve çift tıkla → **Genel** sekmesi → **"Kullanıcı oturum açmış olsun ya da olmasın çalıştır"** seç → Tamam (parola isteyebilir).

> Daha sık çalıştırmak istersen: görev → Tetikleyiciler → Düzenle → "Repeat task every" → süre seç (örn. 6 saat), "Indefinitely".

## 6. GÖREV 2 — Telegram botu (açılışta otomatik başlar)

Bot sürekli açık kalmalı. Bu görev, sunucu her açıldığında botu arka planda başlatır.

1. Görev Zamanlayıcı → **"Temel Görev Oluştur"**.
2. Ad: `YTMusic Bot` → İleri.
3. Tetikleyici: **"Bilgisayar başlatıldığında"** (When the computer starts) → İleri.
4. Eylem: **"Program başlat"** → İleri.
5. Program/komut dosyası: `C:\ytmusic-sync\run_bot.bat`
6. Başlangıç konumu: `C:\ytmusic-sync`
7. İleri → Son.
8. Göreve çift tıkla → **Genel** sekmesi → **"Kullanıcı oturum açmış olsun ya da olmasın çalıştır"** seç.
9. **Koşullar** (Conditions) sekmesi → "Yalnızca AC gücündeyse çalıştır" işaretini **kaldır**.
10. Tamam.

> **Dikkat:** Bu görevi test ederken elle açtığın bot penceresi varsa önce kapat (Ctrl+C). Aynı anda iki bot çalışırsa Telegram mesajlarını çekmek için çakışırlar.

## 7. Test

- GÖREV 1: sağ tık → **Çalıştır** → sonra `type C:\ytmusic-sync\sync.log` ile çıktıyı kontrol et.
- GÖREV 2: sağ tık → **Çalıştır** → Telegram'a "🤖 Bot aktif" mesajı düşmeli.
- Kesin test: sunucuyu yeniden başlat, açılınca Telegram'dan `/menu` yaz — bot cevap veriyorsa açılışta başlamış demektir.

## Notlar

- **Karakter kodlaması:** `.bat` dosyaları `chcp 65001` ve `PYTHONUTF8=1` ile Türkçe/özel karakterleri destekler.
- **browser.json** zamanla geçersizleşebilir (Google oturumu düşerse). "Yetkilendirme hatası" görülürse `setup_yt_browser.py` ile yenile.
- **Silme davranışı:** Fark-bazlı çalışır — Spotify'dan çıkardığın şarkı YouTube'dan da silinir (yalnızca programın eklediği şarkılar; elle eklediklerin korunur). Silmeyi kapatmak için `run_sync.bat` içindeki komuta `--no-delete` ekle.
- **Loglar:** Her senkron `sync.log`'a yazılır. Dosya büyürse `del sync.log` ile temizleyebilirsin.
