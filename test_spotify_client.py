import sys
import unittest
import importlib
from unittest.mock import MagicMock

sys.modules.setdefault("spotipy", MagicMock())
sys.modules.setdefault("spotipy.oauth2", MagicMock())
sys.modules.setdefault("config", MagicMock())

import spotify_client


class TestSpotifyClient(unittest.TestCase):
    def test_remove_deletes_only_last_matching_occurrence(self):
        client = importlib.reload(spotify_client)
        sp = MagicMock()
        sp.playlist_items.return_value = {
            "items": [
                {"track": {"uri": "spotify:track:song"}},
                {"track": {"uri": "spotify:track:other"}},
                {"track": {"uri": "spotify:track:song"}},
            ],
            "next": None,
        }

        self.assertTrue(client.remove_from_playlist(sp, "playlist", "song"))
        sp.playlist_remove_specific_occurrences_of_items.assert_called_once_with(
            "playlist", [{"uri": "spotify:track:song", "positions": [2]}]
        )


if __name__ == "__main__":
    unittest.main()
