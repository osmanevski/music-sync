"""Music-Sync botunda Ozan koprusu (bot.py tarafindan kullanilir, root olarak calisir).

- Komut olmayan metin -> Ozan'a (`hermes -p ozan chat`, kalici "telegram" oturumu), cevap bota.
- Ozan'in giden kutusu (dinleme.telegram_giden) -> bot uzerinden Osman'a.
Isler tek is parcaciginda sirayla yurur; polling dongusu bloklanmaz.
"""
import collections
import os
import queue
import re
import subprocess
import threading
import time

from dinleme import telegram_giden

HERMES_BIN = "/usr/local/lib/hermes-agent/.hermes/bin/hermes"
HERMES_HOME = "/var/lib/hermes"
SESSION = os.environ.get("OZAN_TG_SESSION", "ozan-telegram")
TIMEOUT = 600
_SESSION_LINE = re.compile(r"^\s*session_id:\s*\S+\s*$", re.M)


def ozan_command(text):
    return ["sudo", "-u", "hermes", "env", "-i", f"HOME={HERMES_HOME}", "USER=hermes",
            f"HERMES_HOME={HERMES_HOME}", "PATH=/usr/local/bin:/usr/bin:/bin",
            HERMES_BIN, "-p", "ozan", "chat", "-Q", "--source", "telegram",
            "-c", SESSION, "--create-if-missing", "-q", text]


def clean_reply(out):
    out = _SESSION_LINE.sub("", out or "").strip()
    return out or "(Ozan bos cevap dondu)"


def with_context(text, recent):
    if not recent:
        return text
    lines = "\n".join(f"- {m}" for m in recent)
    return (f"[Bu sohbetin disinda (rutin/cron) Osman'a Telegram'dan gonderdigin son mesajlar:\n{lines}]\n\n"
            f"Osman (Telegram): {text}")


class OzanBridge:
    def __init__(self, send_plain, typing, runner=None, take=telegram_giden.take):
        self.send_plain = send_plain     # fn(text)
        self.typing = typing             # fn()
        self.runner = runner or self._run
        self.take = take
        self.jobs = queue.Queue()
        self.recent = collections.deque(maxlen=5)   # Ozan'in sohbet disi giden mesajlari

    def start(self):
        threading.Thread(target=self._worker, daemon=True, name="ozan").start()
        threading.Thread(target=self._outbox_loop, daemon=True, name="ozan-giden").start()

    def ask(self, text):
        self.jobs.put(text)

    def _run(self, text):
        r = subprocess.run(ozan_command(text), capture_output=True, text=True, timeout=TIMEOUT,
                           cwd=HERMES_HOME)
        if r.returncode != 0 and not r.stdout.strip():
            raise RuntimeError((r.stderr or "").strip()[-300:] or f"cikis {r.returncode}")
        return r.stdout

    def handle(self, text):
        recent = list(self.recent)
        self.recent.clear()
        done = threading.Event()

        def keep_typing():
            while not done.wait(4.5):
                self.typing()
        self.typing()
        threading.Thread(target=keep_typing, daemon=True).start()
        try:
            reply = clean_reply(self.runner(with_context(text, recent)))
        except subprocess.TimeoutExpired:
            reply = "Ozan: 10 dakikada bitiremedim, isi yarida biraktim. Tekrar sorar misin?"
        except Exception as e:
            reply = f"Ozan: bir hata oldu ({type(e).__name__}: {str(e)[:200]})"
        finally:
            done.set()
        for part in telegram_giden.chunks(reply):
            self.send_plain(part)

    def _worker(self):
        while True:
            text = self.jobs.get()
            try:
                self.handle(text)
            except Exception as e:
                print(f"ozan worker hata: {e}")

    def flush_outbox(self):
        for msg in self.take():
            self.recent.append(msg[:500])
            for part in telegram_giden.chunks(msg):
                self.send_plain(part)

    def _outbox_loop(self):
        while True:
            try:
                self.flush_outbox()
            except Exception as e:
                print(f"ozan giden hata: {e}")
            time.sleep(3)
