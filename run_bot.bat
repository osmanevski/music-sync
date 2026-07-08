@echo off
REM Telegram komut botunu baslatir. Surekli acik kalmali.
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d C:\ytmusic-sync
call venv\Scripts\activate.bat
python bot.py
pause
