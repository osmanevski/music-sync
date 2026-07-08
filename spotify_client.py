"""
Spotify Web API istemcisi (spotipy uzerinden).
Playlist'leri ve icindeki sarkilari ceker.
"""
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import config


def get_client():
    auth = SpotifyOAuth(
        client_id=config.SPOTIFY_CLIENT_ID,
        client_secret=config.SPOTIFY_CLIENT_SECRET,
        redirect_uri=config.SPOTIFY_REDIRECT_URI,
        scope=config.SPOTIFY_SCOPE,
        cache_path=".spotify_cache",
        open_browser=True,
    )
    return spotipy.Spotify(auth_manager=auth)


def list_playlists(sp):
    """Kullanicinin tum playlist'lerini dondur: [{id, name, snapshot_id, track_count}]"""
    playlists = []
    results = sp.current_user_playlists(limit=50)
    while results:
        for pl in results["items"]:
            playlists.append({
                "id": pl["id"],
                "name": pl["name"],
                "snapshot_id": pl["snapshot_id"],
                "track_count": pl["tracks"]["total"],
            })
        results = sp.next(results) if results["next"] else None
    return playlists


def get_playlist_snapshot(sp, playlist_id):
    """Sadece snapshot_id'yi cek - degisiklik kontrolu icin (ucuz)."""
    pl = sp.playlist(playlist_id, fields="snapshot_id")
    return pl["snapshot_id"]


def get_tracks(sp, playlist_id):
    """
    Playlist icindeki tum sarkilari dondur:
    [{id, name, artists, duration_sec}]
    artists: virgulle birlesik sanatci isimleri
    """
    tracks = []
    results = sp.playlist_items(
        playlist_id,
        fields="items(track(id,name,duration_ms,artists(name))),next",
        additional_types=["track"],
    )
    while results:
        for item in results["items"]:
            t = item.get("track")
            if not t or not t.get("id"):
                continue  # bazen None gelir (kaldirilmis/lokal sarki)
            # Sanatci adlari bazen None gelebilir; bunlari ele
            artist_names = [
                a.get("name") for a in (t.get("artists") or [])
                if a and a.get("name")
            ]
            tracks.append({
                "id": t["id"],
                "name": t.get("name") or "",
                "artists": ", ".join(artist_names),
                "duration_sec": round((t.get("duration_ms") or 0) / 1000),
            })
        results = sp.next(results) if results.get("next") else None
    return tracks
