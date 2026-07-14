@echo off
REM ==================================================================
REM  Spotify -> YouTube Music otomatik senkronizasyon (Windows)
REM  Gorev Zamanlayici (Task Scheduler) bunu her gun 03:00'te cagirir.
REM ==================================================================

REM Konsolu UTF-8 yap (Turkce/Yunanca karakterler icin)
chcp 65001 >nul

REM Python ciktisini da UTF-8'e zorla
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

REM Bu satiri kendi proje klasorunun TAM yoluyla degistir:
cd /d C:\ytmusic-sync

REM Sanal ortami aktif et (venv Windows'ta farkli yolda)
call venv\Scripts\activate.bat

REM watchlist'teki listeleri senkronize et (ekleme/silme), ciktiyi log'a yaz
python sync.py >> sync.log 2>&1

REM Bitti
