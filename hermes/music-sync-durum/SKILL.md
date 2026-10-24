---
name: music-sync-durum
description: "Music Sync (Spotify → YouTube Music) senkron durumunu salt-okunur sorgula. 'Bu şarkı YouTube'a geçti mi', 'dün gece senkron çalıştı mı', 'Karmaşık'ta eşleşmeyen var mı', 'music sync durumu', 'bekleyen eşleşmeler' taleplerinde kullan."
version: 1.0.0
author: Osman
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [Music Sync, Spotify, YouTube Music, Senkron]
---

# Music Sync durumu

Music Sync her gece 03:00'te Osman'ın takip edilen Spotify listelerine yeni
eklenen şarkıları YouTube Music'teki aynı adlı listeye taşır. Emin olamadığı
eşleşmeyi **şüpheli** diye ayırır; o şarkı YouTube'a geçmez, Osman Music-Sync
botunda `/review` ile onaylayana kadar bekler.

Osman şarkıyı Spotify'da kendisi listeye ekler. Sen yalnız durumu söylersin:
**hiçbir şey ekleme, silme, sıralama; Spotify'a ya da YouTube'a yazma.**

## Araç (salt-okunur, sudo gerekmez)

```bash
python3 /opt/music-sync/durum.py ozet              # son gece senkronu + liste başına sayılar
python3 /opt/music-sync/durum.py ara "<şarkı/sanatçı>"   # YouTube'a geçti mi, inceleme mi bekliyor
python3 /opt/music-sync/durum.py bekleyen [liste]  # şüpheli eşleşmeler (ör. bekleyen karmaşık)
```

Arama Türkçe harf ve büyük/küçük harf farkını yok sayar; birden çok sözcük
verilirse hepsi şarkı adı + sanatçıda geçmeli.

## Cevaplarken

- `ara` "kaydında yok" derse üç ihtimal var: şarkı bu gece eklendi ve 03:00
  senkronu henüz çalışmadı; şarkı takip edilmeyen bir listede; ya da şarkı
  YouTube listesinde Music Sync takibe başlamadan önce de vardı (kayıt yalnız
  Music Sync'in eklediklerini tutar). Hangi Spotify listesinde olduğunu
  `spotify_playlists` ile okuyabilirsin (yalnız okuma).
- Liste başına "geçmiş" sayısı Music Sync'in eklediği şarkı sayısıdır, YouTube
  listesinin toplam boyu değil.
- Son çalışmada `TAMAMLANMADI` ya da hata satırı varsa bunu açıkça söyle.
  `Temporary failure in name resolution` / `Network is unreachable` sunucunun
  gece ağ kopmasıdır, Music Sync hatası değil.
- Şüpheli eşleşmeyi sen onaylama; onay Music-Sync botunda `/review`.
- Kısa cevap ver: Osman "geçti mi" diye sorduysa evet/hayır + liste + tarih yeter.
