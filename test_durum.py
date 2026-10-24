import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import durum

JOURNAL = """\
2026-10-24T03:00:01+03:00 servis-sunucu systemd[1]: Starting music-sync-sync.service - Music Sync daily...
2026-10-24T03:00:06+03:00 servis-sunucu python[1]: Takip edilen 3 liste senkronlaniyor.
2026-10-24T03:00:06+03:00 servis-sunucu python[1]: [SENKRON] 'Deli Kızım Uyan' (36 sarki)
2026-10-24T03:00:07+03:00 servis-sunucu python[1]:   (Degisiklik yok.)
2026-10-24T03:00:09+03:00 servis-sunucu python[1]: [SENKRON] '53' (256 sarki)
2026-10-24T03:00:11+03:00 servis-sunucu python[1]:   (2 yeni sarki tespit edildi.)
2026-10-24T03:00:13+03:00 servis-sunucu python[1]:   + Bedia Akartürk - Kesik Çayır  (skor 100.0)
2026-10-24T03:00:13+03:00 servis-sunucu python[1]:   ? SUPHELI: Aysun Gültekin - Ağlama Gözlerim  (en iyi skor 61)
2026-10-24T03:00:13+03:00 servis-sunucu python[1]:   -> Eklendi: 1 | Supheli: 1 | Silindi: 0
2026-10-24T03:00:45+03:00 servis-sunucu python[1]: [SIRA] 'Deli Kızım Uyan' zaten sirali.
2026-10-24T03:00:48+03:00 servis-sunucu python[1]: [SIRA] 1 yeni sarki en uste alindi
2026-10-24T03:01:31+03:00 servis-sunucu python[1]:   ! Siralama hatasi 'Karmaşık Liste': Read timed out.
2026-10-24T03:04:14+03:00 servis-sunucu python[1]: Bitti. Supheli eslesmeleri gormek icin: python review.py
"""


def make_db(path):
    c = sqlite3.connect(path)
    c.executescript("""
        CREATE TABLE synced_tracks (spotify_track_id TEXT, yt_playlist_id TEXT, yt_video_id TEXT,
            track_name TEXT, artist_name TEXT, synced_at TIMESTAMP);
        CREATE TABLE pending_review (id INTEGER PRIMARY KEY, spotify_track_id TEXT, yt_playlist_id TEXT,
            track_name TEXT, artist_name TEXT, spotify_duration INTEGER, candidates_json TEXT, created_at TIMESTAMP);
        CREATE TABLE playlist_snapshots (spotify_playlist_id TEXT, snapshot_id TEXT, yt_playlist_id TEXT, updated_at TIMESTAMP);
    """)
    c.execute("INSERT INTO synced_tracks VALUES ('s1','YT53','v1','Kesik Çayır','Bedia Akartürk','2026-10-24 00:00:13')")
    c.execute("INSERT INTO synced_tracks VALUES ('s2','YTKAR','v2','İstanbul','Zeki Müren','2026-10-20 00:00:00')")
    c.execute("INSERT INTO pending_review VALUES (1,'s3','YT53','Ağlama Gözlerim','Aysun Gültekin',200,'[]','2026-10-24 00:00:13')")
    c.execute("INSERT INTO playlist_snapshots VALUES ('SP53','x','YT53','')")
    c.execute("INSERT INTO playlist_snapshots VALUES ('SPKAR','x','YTKAR','')")
    c.commit()
    c.close()


class DurumTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.db = self.dir / "sync.db"
        make_db(self.db)
        self.durum = self.dir / "durum"
        names = {"SP53": "53", "SPKAR": "Karmaşık Liste"}
        out = durum.cmd_kaydet("inv", db=self.db, durum_dir=self.durum, journal=JOURNAL,
                               fetch=lambda sp: names[sp])
        self.assertIn("2 liste adı", out)

    def tearDown(self):
        self.tmp.cleanup()

    def test_norm_turkish(self):
        self.assertEqual(durum.norm("İSTANBUL"), durum.norm("istanbul"))
        self.assertEqual(durum.norm("AĞLAMA ışık"), "aglama isik")

    def test_parse_run(self):
        run = durum.parse_run(JOURNAL)
        self.assertTrue(run["bitti"])
        self.assertEqual(len(run["listeler"]), 2)
        self.assertEqual(run["eklenen"], [("53", "Bedia Akartürk - Kesik Çayır")])
        self.assertEqual(run["supheli"], [("53", "Aysun Gültekin - Ağlama Gözlerim")])
        self.assertEqual(len(run["hatalar"]), 1)
        self.assertIn("1 yeni sarki en uste alindi", run["sira"])

    def test_unfinished_run_is_flagged(self):
        text = "\n".join(JOURNAL.splitlines()[:6])
        self.assertFalse(durum.parse_run(text)["bitti"])

    def test_ozet(self):
        out = durum.cmd_ozet(db=self.db, durum_dir=self.durum)
        self.assertIn("tamamlandı", out)
        self.assertIn("eklenen 1", out)
        self.assertIn("Karmaşık Liste: 1 geçmiş", out)
        self.assertIn("53: 1 geçmiş, 1 bekliyor", out)
        self.assertIn("1 yeni sarki en uste alindi", out)

    def test_ara_synced_case_and_diacritics(self):
        out = durum.cmd_ara("istanbul zeki", db=self.db, durum_dir=self.durum)
        self.assertIn("✓ Zeki Müren - İstanbul", out)
        self.assertIn("Karmaşık Liste", out)

    def test_ara_pending(self):
        out = durum.cmd_ara("aglama", db=self.db, durum_dir=self.durum)
        self.assertIn("GEÇMEDİ", out)

    def test_ara_missing(self):
        self.assertIn("kaydında yok", durum.cmd_ara("yokboylesarki", db=self.db, durum_dir=self.durum))

    def test_bekleyen_filter(self):
        self.assertIn("Ağlama Gözlerim", durum.cmd_bekleyen("53", db=self.db, durum_dir=self.durum))
        self.assertIn("yok", durum.cmd_bekleyen("Karmaşık", db=self.db, durum_dir=self.durum))

    def test_kaydet_keeps_old_name_when_offline(self):
        def offline(sp):
            raise OSError("ağ yok")
        durum.cmd_kaydet("inv", db=self.db, durum_dir=self.durum, journal=JOURNAL, fetch=offline)
        data = json.loads((self.durum / "listeler.json").read_text(encoding="utf-8"))
        self.assertEqual(data["SPKAR"]["ad"], "Karmaşık Liste")

    def test_readonly_db(self):
        conn = durum.open_db(self.db)
        with self.assertRaises(sqlite3.OperationalError):
            conn.execute("DELETE FROM synced_tracks")
        conn.close()

    def test_log_rotation(self):
        for i in range(20):
            (self.durum / f"calisma-2026-01-{i:02d}-0300.log").write_text("x")
        durum.cmd_kaydet("inv", db=self.db, durum_dir=self.durum, journal=JOURNAL, fetch=lambda sp: "a")
        self.assertEqual(len(list(self.durum.glob("calisma-*.log"))), durum.LOG_KEEP)


if __name__ == "__main__":
    unittest.main()
