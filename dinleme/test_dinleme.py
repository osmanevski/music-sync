import json
import os
import sqlite3
import tempfile
import unittest

from dinleme import calistir, siniflandir, topla


def dump(ids, t="2026-10-24T00:00:00+00:00"):
    return {"ok": True, "fetched_at": t, "items": [{"id": i, "title": f"t-{i}", "duration": 200} for i in ids]}


class CountNew(unittest.TestCase):
    def test_unchanged(self):
        self.assertEqual(topla.count_new_on_top(list("abcdef"), list("abcdef")), 0)

    def test_two_new(self):
        self.assertEqual(topla.count_new_on_top(list("abcdef"), list("xyabcd")), 2)

    def test_rewatched_moves_to_top(self):
        # c tekrar izlendi: eski yerinden silinip basa geldi, ustune x izlendi
        self.assertEqual(topla.count_new_on_top(list("abcdefg"), list("xcabdefg")), 2)

    def test_no_anchor(self):
        self.assertIsNone(topla.count_new_on_top(list("abcdef"), list("uvwxyz")))


class Ingest(unittest.TestCase):
    def setUp(self):
        self.db = topla.connect(":memory:")

    def plays(self, kind=None):
        q = "SELECT item_id FROM plays WHERE platform='youtube'" + (f" AND kind='{kind}'" if kind else "")
        return [r[0] for r in self.db.execute(q + " ORDER BY id")]

    def test_first_run_backfills_then_live(self):
        r = topla.ingest_youtube(self.db, dump(list("abcd")))
        self.assertEqual((r["mode"], r["new"]), ("first", 4))
        r = topla.ingest_youtube(self.db, dump(list("xaabcd")))
        self.assertEqual((r["mode"], r["new"]), ("live", 2))
        self.assertEqual(self.plays("live"), ["x", "a"])

    def test_repeats_counted(self):
        topla.ingest_youtube(self.db, dump(list("abcd")))
        topla.ingest_youtube(self.db, dump(list("aabcd")))
        topla.ingest_youtube(self.db, dump(list("aaabcd")))
        self.assertEqual(self.plays("live"), ["a", "a"])

    def test_error_dump(self):
        r = topla.ingest_youtube(self.db, {"ok": False, "error": "Sign in", "auth_error": True, "items": []})
        self.assertEqual(r["mode"], "error")
        self.assertTrue(r["auth_error"])

    def test_spotify_dedupe_and_skip_episode(self):
        items = [{"played_at": "2026-10-23T22:44:00Z", "track": {"id": "t1", "name": "Kesik Çayır",
                  "artists": [{"name": "Bedia Akartürk"}], "album": {"name": "A"}, "duration_ms": 1, "type": "track"}},
                 {"played_at": "2026-10-23T22:40:00Z", "track": {"id": "e1", "type": "episode"}}]
        self.assertEqual(topla.ingest_spotify(self.db, items), 1)
        self.assertEqual(topla.ingest_spotify(self.db, items), 0)
        artists = json.loads(self.db.execute("SELECT artists FROM tracks").fetchone()[0])
        self.assertEqual(artists, ["Bedia Akartürk"])

    def test_classification_apply_and_fail_counter(self):
        topla.ingest_youtube(self.db, dump(["v1", "v2", "v3"]))
        n = topla.apply_classification(self.db, [
            {"id": "v1", "muzik": True, "sanatcilar": ["Aysun Gültekin"], "eser": "Allı Turnam"},
            {"id": "v2", "muzik": False},
            {"id": "zzz", "muzik": True}], ["v1", "v2", "v3"])
        self.assertEqual(n, 2)
        row = self.db.execute("SELECT is_music, artists, work FROM videos WHERE id='v1'").fetchone()
        self.assertEqual(row, (1, '["Aysun Gültekin"]', "Allı Turnam"))
        self.assertEqual(self.db.execute("SELECT classify_fails FROM videos WHERE id='v3'").fetchone()[0], 1)
        self.assertEqual([v[0] for v in topla.unclassified_videos(self.db)], ["v3"])


class Classifier(unittest.TestCase):
    def test_parse_fenced(self):
        out = siniflandir.parse_reply('```json\n[{"id":"a","muzik":false}]\n```')
        self.assertEqual(out, [{"id": "a", "muzik": False}])

    def test_classify_uses_haiku(self):
        seen = {}

        class R:
            returncode = 0
            stdout = json.dumps({"is_error": False, "result": '[{"id":"a","muzik":true,"sanatcilar":["X"],"eser":"Y"}]'})
            stderr = ""

        def fake_run(cmd, **kw):
            seen["cmd"] = cmd
            return R()
        out = siniflandir.classify([("a", "X - Y", 200)], run=fake_run)
        self.assertIn("claude-haiku-5-5", seen["cmd"])
        self.assertEqual(out[0]["eser"], "Y")


class RunLoop(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.db = os.path.join(self.dir, "d.db")
        self.dump = os.path.join(self.dir, "y.json")

    def write(self, data):
        with open(self.dump, "w") as f:
            json.dump(data, f)

    def test_auth_alert_once_and_recovery(self):
        self.write({"ok": False, "auth_error": True, "error": "Sign in", "items": [], "fetched_at": "x"})
        alerts = []
        for _ in range(4):
            _, a = calistir.run(self.db, self.dump, lambda: [], lambda v: [])
            alerts += a
        self.assertEqual(len(alerts), 1)
        self.assertIn("oturumu", alerts[0])
        self.write(dump(["a"], t="y"))
        _, a = calistir.run(self.db, self.dump, lambda: [], lambda v: [{"id": "a", "muzik": False}])
        self.assertEqual(len(a), 1)
        self.assertIn("yeniden", a[0])

    def test_same_dump_not_double_counted(self):
        self.write(dump(list("abc")))
        calistir.run(self.db, self.dump, lambda: [], lambda v: [])
        self.write(dump(list("xabc"), t="t2"))
        calistir.run(self.db, self.dump, lambda: [], lambda v: [])
        calistir.run(self.db, self.dump, lambda: [], lambda v: [])
        n = sqlite3.connect(self.db).execute("SELECT COUNT(*) FROM plays WHERE kind='live'").fetchone()[0]
        self.assertEqual(n, 1)


class Radyo(unittest.TestCase):
    def test_revision_added_for_queue_actions(self):
        from dinleme import radyo
        body = radyo.build_action("move", ["id=abc", "before=null"], lambda: {"revision": "r1"})
        self.assertEqual(body, {"action": "move", "id": "abc", "before": None, "revision": "r1"})
        body = radyo.build_action("add", ["url=https://www.youtube.com/watch?v=x"], lambda: 1 / 0)
        self.assertNotIn("revision", body)
        body = radyo.build_action("repeat", ["id=a", "repeat=true"], lambda: {"revision": "r"})
        self.assertIs(body["repeat"], True)

    def test_unknown_action_rejected(self):
        from dinleme import radyo
        with self.assertRaises(ValueError):
            radyo.build_action("mesaj_sil", [], lambda: {})


if __name__ == "__main__":
    unittest.main()
