import sys
import unittest
from unittest.mock import MagicMock, patch

sys.modules.setdefault("spotipy", MagicMock())
sys.modules.setdefault("spotipy.oauth2", MagicMock())
sys.modules.setdefault("dotenv", MagicMock())

import sort_playlists


def apply(items, moves):
    items = list(items)
    for j, i in moves:
        items.insert(i, items.pop(j))
    return items


class TestFloatNewToTop(unittest.TestCase):
    def test_single_new_song_at_end_goes_to_top(self):
        moves = sort_playlists.plan_float_moves([4])
        self.assertEqual(moves, [(4, 0)])
        self.assertEqual(apply("abcdE", moves), list("Eabcd"))

    def test_several_new_songs_newest_first_rest_keeps_order(self):
        moves = sort_playlists.plan_float_moves([3, 4, 5])
        self.assertEqual(apply("abcXYZ", moves), list("ZYXabc"))

    def test_scattered_new_songs(self):
        moves = sort_playlists.plan_float_moves([1, 4])
        self.assertEqual(apply("aXbcY", moves), list("YXabc"))

    def test_already_on_top_needs_no_moves(self):
        self.assertEqual(sort_playlists.plan_float_moves([0]), [])
        self.assertEqual(sort_playlists.plan_float_moves([0, 1]), [])

    def test_skips_protected_and_unlisted(self):
        sp = MagicMock()
        with patch.object(sort_playlists, "read_sort_ids", return_value={"p1", "p2"}):
            snap = sort_playlists.float_new_to_top(sp, {"id": "p1", "name": "ϟ FIRTINA"}, [3], "s0")
            snap2 = sort_playlists.float_new_to_top(sp, {"id": "zz", "name": "Diger"}, [3], "s0")
        self.assertEqual((snap, snap2), ("s0", "s0"))
        sp.playlist_reorder_items.assert_not_called()

    def test_reorders_and_returns_new_snapshot(self):
        sp = MagicMock()
        sp.playlist_reorder_items.return_value = {"snapshot_id": "s1"}
        with patch.object(sort_playlists, "read_sort_ids", return_value={"p2"}):
            snap = sort_playlists.float_new_to_top(sp, {"id": "p2", "name": "Karmaşık Liste"}, [9], "s0")
        sp.playlist_reorder_items.assert_called_once_with(
            "p2", range_start=9, insert_before=0, range_length=1, snapshot_id="s0")
        self.assertEqual(snap, "s1")


if __name__ == "__main__":
    unittest.main()
