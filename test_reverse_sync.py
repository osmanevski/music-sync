import sys
import unittest
from unittest.mock import MagicMock

sys.modules.setdefault("spotipy", MagicMock())
sys.modules.setdefault("spotipy.oauth2", MagicMock())
sys.modules.setdefault("ytmusicapi", MagicMock())
mock_dotenv = MagicMock()
mock_dotenv.load_dotenv = MagicMock()
sys.modules.setdefault("dotenv", mock_dotenv)

import reverse_sync


class TestReverseSync(unittest.TestCase):
    def setUp(self):
        self.sp = MagicMock()
        self.yt = MagicMock()
        self.playlist = {"id": "yt-list", "name": "Mix", "track_count": 2}

    def test_first_sync_adds_match_and_retries_pending_next_time(self):
        tracks = [
            {"id": "yt-ok", "name": "Song", "artists": "Artist", "duration_sec": 180},
            {"id": "yt-low", "name": "Unknown", "artists": "Nobody", "duration_sec": 200},
        ]
        reverse_sync.ytc.get_tracks = MagicMock(return_value=tracks)
        reverse_sync.db.get_reverse_track_state = MagicMock(return_value=None)
        reverse_sync.spc.get_or_create_playlist = MagicMock(return_value=("sp-list", False))
        reverse_sync.spc.get_tracks = MagicMock(return_value=[])
        reverse_sync.spc.search_tracks = MagicMock(side_effect=[[{"spotify_id": "sp-ok"}], []])
        reverse_sync.matcher.best_match = MagicMock(side_effect=[
            ({"spotify_id": "sp-ok", "title": "Song", "artists": "Artist"}, 95, []),
            (None, 0, []),
        ])
        reverse_sync.spc.add_to_playlist = MagicMock(return_value=True)
        reverse_sync.db.mark_reverse_synced = MagicMock()
        reverse_sync.db.set_reverse_track_state = MagicMock()

        result = reverse_sync.sync_playlist(self.sp, self.yt, self.playlist)

        self.assertEqual(result["added"], 1)
        self.assertEqual(result["pending"], 1)
        reverse_sync.db.set_reverse_track_state.assert_called_once_with("yt-list", {"yt-ok"})

    def test_removed_track_is_deleted_only_when_owned_by_reverse_sync(self):
        reverse_sync.ytc.get_tracks = MagicMock(return_value=[])
        reverse_sync.db.get_reverse_track_state = MagicMock(return_value={"owned", "manual"})
        reverse_sync.spc.get_or_create_playlist = MagicMock(return_value=("sp-list", True))
        reverse_sync.spc.get_tracks = MagicMock(return_value=[])
        reverse_sync.db.get_reverse_synced = MagicMock(return_value=[{
            "yt_video_id": "owned", "spotify_track_id": "sp-owned"
        }])
        reverse_sync.spc.remove_from_playlist = MagicMock(return_value=True)
        reverse_sync.db.remove_reverse_synced = MagicMock()
        reverse_sync.db.set_reverse_track_state = MagicMock()

        result = reverse_sync.sync_playlist(self.sp, self.yt, self.playlist)

        self.assertEqual(result["removed"], 1)
        reverse_sync.spc.remove_from_playlist.assert_called_once_with(
            self.sp, "sp-list", "sp-owned"
        )


if __name__ == "__main__":
    unittest.main()
