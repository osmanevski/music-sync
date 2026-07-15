import sys
import unittest
from unittest.mock import MagicMock, patch

# Mock external dependencies to allow running in sandboxed environment without pip installs
mock_ytmusicapi = MagicMock()
sys.modules['ytmusicapi'] = mock_ytmusicapi
sys.modules['config'] = MagicMock()

from ytmusic_client import add_to_playlist

class TestYTMusicClient(unittest.TestCase):
    @patch('time.sleep', return_value=None)
    def test_add_to_playlist_success_string(self, mock_sleep):
        yt = MagicMock()
        yt.add_playlist_items.return_value = "STATUS_SUCCEEDED"
        
        ok, already_exists = add_to_playlist(yt, "playlist_id", "video_id", retries=2)
        self.assertTrue(ok)
        self.assertFalse(already_exists)
        yt.add_playlist_items.assert_called_once_with("playlist_id", ["video_id"], duplicates=False)

    @patch('time.sleep', return_value=None)
    def test_add_to_playlist_success_dict(self, mock_sleep):
        yt = MagicMock()
        yt.add_playlist_items.return_value = {"status": "STATUS_SUCCEEDED"}
        
        ok, already_exists = add_to_playlist(yt, "playlist_id", "video_id", retries=2)
        self.assertTrue(ok)
        self.assertFalse(already_exists)
        yt.add_playlist_items.assert_called_once_with("playlist_id", ["video_id"], duplicates=False)

    @patch('time.sleep', return_value=None)
    def test_add_to_playlist_fail_status(self, mock_sleep):
        yt = MagicMock()
        yt.add_playlist_items.return_value = "STATUS_FAILED"
        
        ok, already_exists = add_to_playlist(yt, "playlist_id", "video_id", retries=1)
        self.assertFalse(ok)
        self.assertFalse(already_exists)
        self.assertEqual(yt.add_playlist_items.call_count, 2)  # Initial attempt + 1 retry

    @patch('time.sleep', return_value=None)
    def test_add_to_playlist_conflict_exception(self, mock_sleep):
        yt = MagicMock()
        yt.add_playlist_items.side_effect = Exception("HTTP 409 Conflict: Already exists")
        
        ok, already_exists = add_to_playlist(yt, "playlist_id", "video_id", retries=2)
        self.assertTrue(ok)
        self.assertTrue(already_exists)
        yt.add_playlist_items.assert_called_once_with("playlist_id", ["video_id"], duplicates=False)

    @patch('time.sleep', return_value=None)
    def test_add_to_playlist_retry_then_success(self, mock_sleep):
        yt = MagicMock()
        # First call fails with generic exception, second call succeeds
        yt.add_playlist_items.side_effect = [Exception("Temporary error"), "STATUS_SUCCEEDED"]
        
        ok, already_exists = add_to_playlist(yt, "playlist_id", "video_id", retries=2)
        self.assertTrue(ok)
        self.assertFalse(already_exists)
        self.assertEqual(yt.add_playlist_items.call_count, 2)
        mock_sleep.assert_called_once_with(1.5)

if __name__ == '__main__':
    unittest.main()
