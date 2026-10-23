"""Saatlik toplama turu: dokum + Spotify + siniflandirma, uyari metinleri doner.

Uyari yalniz bir ariza serisi esige ulastiginda bir kez ve duzeldiginde bir kez uretilir.
"""
import json
import os

from . import topla

THRESHOLDS = {"youtube": 3, "youtube_auth": 2, "spotify": 3, "siniflandirma": 3}
MESSAGES = {
    "youtube_auth": "YouTube oturumu dustu (izleme gecmisi okunamiyor). Music Sync'in browser.json "
                    "cerezlerini yenilemek gerekiyor; o zamana kadar YouTube dinlemeleri kaydedilmiyor.",
    "youtube": "YouTube izleme gecmisi 3 saattir okunamiyor: {err}",
    "spotify": "Spotify son dinlenenler 3 saattir okunamiyor: {err}",
    "siniflandirma": "Muzik ayirma (Haiku) 3 denemedir basarisiz: {err}",
}


def _streak(db, key, failed, err, out):
    streaks = topla.get_state(db, "ariza", {})
    s = streaks.get(key, {"n": 0, "alerted": False})
    if failed:
        s["n"] += 1
        if s["n"] >= THRESHOLDS[key] and not s["alerted"]:
            out.append("Ozan: " + MESSAGES[key].format(err=err))
            s["alerted"] = True
    else:
        if s.get("alerted"):
            out.append(f"Ozan: {key} yeniden calisiyor.")
        s = {"n": 0, "alerted": False}
    streaks[key] = s
    topla.set_state(db, "ariza", streaks)


def read_dump(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        return {"ok": False, "error": f"dokum okunamadi: {e}", "items": []}


def run(db_path, dump_path, spotify_fetch, classify_fn, batch=40):
    """Doner: (ozet dict, uyari satirlari listesi)."""
    alerts, summary = [], {}
    db = topla.connect(db_path)
    try:
        dump = read_dump(dump_path)
        last = topla.get_state(db, "yt_dump_seen")
        if dump.get("ok") and dump.get("fetched_at") == last:
            yt = {"new": 0, "mode": "ayni-dokum", "error": None, "auth_error": False}
        else:
            yt = topla.ingest_youtube(db, dump)
            if dump.get("ok"):
                topla.set_state(db, "yt_dump_seen", dump.get("fetched_at"))
        summary["youtube"] = yt
        auth = yt["mode"] == "error" and yt.get("auth_error")
        _streak(db, "youtube_auth", auth, yt.get("error"), alerts)
        _streak(db, "youtube", yt["mode"] == "error" and not auth, yt.get("error"), alerts)
        db.commit()

        try:
            summary["spotify"] = topla.ingest_spotify(db, spotify_fetch())
            _streak(db, "spotify", False, None, alerts)
        except Exception as e:
            summary["spotify"] = f"hata: {e}"
            _streak(db, "spotify", True, f"{type(e).__name__}: {e}"[:300], alerts)
        db.commit()

        classified, err = 0, None
        for _ in range(10):  # tur basina en fazla 10 parti (ilk calismada ~200 video)
            todo = topla.unclassified_videos(db, limit=batch)
            if not todo:
                break
            try:
                results = classify_fn(todo)
            except Exception as e:
                err = f"{type(e).__name__}: {e}"[:300]
                break
            classified += topla.apply_classification(db, results, [v[0] for v in todo])
            db.commit()
        summary["siniflandirilan"] = classified
        _streak(db, "siniflandirma", err is not None, err, alerts)
        db.commit()
    finally:
        db.close()
    return summary, alerts
