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
                "owner_id": (pl.get("owner") or {}).get("id"),
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


def search_tracks(sp, track_name, artists, limit=None):
    """YouTube kaydina Spotify'da aday ara; matcher ile uyumlu format dondur."""
    limit = limit or config.SEARCH_RESULT_LIMIT
    query = f"track:{track_name} artist:{artists.split(',')[0]}"
    try:
        items = sp.search(q=query, type="track", limit=limit)["tracks"]["items"]
    except Exception:
        items = []
    return [
        {
            "spotify_id": t.get("id"),
            "title": t.get("name") or "",
            "artists": ", ".join(
                a.get("name") for a in (t.get("artists") or []) if a.get("name")
            ),
            "duration_sec": round((t.get("duration_ms") or 0) / 1000),
            "is_music": True,
        }
        for t in items if t.get("id")
    ]


def get_or_create_playlist(sp, name, description="YouTube Music'ten senkronize edildi"):
    """Ayni isimli Spotify listesini bul veya kullanicinin hesabinda olustur."""
    user_id = sp.current_user()["id"]
    for pl in list_playlists(sp):
        if pl["name"] == name and pl.get("owner_id") == user_id:
            return pl["id"], True
    created = sp.user_playlist_create(user_id, name, public=False, description=description)
    return created["id"], False


def add_to_playlist(sp, playlist_id, track_id):
    """Spotify listesine tek parca ekle. Basariliysa True."""
    try:
        sp.playlist_add_items(playlist_id, [f"spotify:track:{track_id}"])
        return True
    except Exception as e:
        print(f"  ! Spotify ekleme hatasi: {e}")
        return False


def remove_from_playlist(sp, playlist_id, track_id):
    """Spotify listesinden yalnizca bir eslesmeyi sil; manuel tekrarları koru."""
    try:
        uri = f"spotify:track:{track_id}"
        positions = []
        offset = 0
        page = sp.playlist_items(playlist_id, fields="items(track(uri)),next", limit=100)
        while page:
            for index, item in enumerate(page.get("items") or []):
                if (item.get("track") or {}).get("uri") == uri:
                    positions.append(offset + index)
            offset += len(page.get("items") or [])
            page = sp.next(page) if page.get("next") else None
        if not positions:
            return True
        # Arac eklemeleri listenin sonuna yaptigi icin en sondaki eslesme en guvenli adaydir.
        sp.playlist_remove_specific_occurrences_of_items(
            playlist_id, [{"uri": uri, "positions": [positions[-1]]}]
        )
        return True
    except Exception as e:
        print(f"  ! Spotify silme hatasi: {e}")
        return False
