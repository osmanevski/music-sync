"""
YouTube Music istemcisi (ytmusicapi uzerinden).

Onemli: VIDEO degil MUZIK ekliyoruz.
ytmusicapi arama sonuclarinda:
  - resultType == "song"  -> gercek muzik (album, sanatci ile)
  - videoType MUSIC_VIDEO_TYPE_ATV -> "Topic" kanalindan ses kaydi (muzik sayilir)
  - videoType MUSIC_VIDEO_TYPE_OMV/UGC -> video (istemiyoruz)

Bu yuzden filter="songs" ile ariyoruz; bu zaten video doner degil sarki dondurur.
Yedek olarak da videoType kontrolu yapiyoruz.
"""
from ytmusicapi import YTMusic
import config

# Muzik kabul edilen videoType'lar
MUSIC_VIDEO_TYPES = {"MUSIC_VIDEO_TYPE_ATV", "MUSIC_VIDEO_TYPE_OFFICIAL_SOURCE_MUSIC"}


def get_client():
    # Browser authentication: browser.json tarayicidan kopyalanan
    # header'lardan olusturulur. OAuth'tan farkli olarak YouTube Music'in
    # ic API'siyle sorunsuz calisir.
    return YTMusic(config.YT_BROWSER_FILE)


def _is_music(result):
    """Bir arama sonucu gercek muzik mi (video degil)?"""
    if result.get("resultType") == "song":
        return True
    vtype = result.get("videoType")
    return vtype in MUSIC_VIDEO_TYPES


def search_song(yt, track_name, artists, limit=None):
    """
    Bir sarkiyi YouTube Music'te ara, aday listesi dondur.
    Once 'songs' filtresiyle arar (bunlar zaten muzik).
    Donen aday formati:
      {title, artists, duration_sec, videoId, is_music}
    """
    limit = limit or config.SEARCH_RESULT_LIMIT
    query = f"{track_name} {artists}"

    candidates = []

    # 1) songs filtresi - bunlar gercek muzik
    try:
        results = yt.search(query, filter="songs", limit=limit)
    except Exception:
        results = []

    for r in results:
        candidates.append(_to_candidate(r, is_music=True))

    # 2) Hic sonuc yoksa genel aramaya dus ama muzik olanlari filtrele
    if not candidates:
        try:
            results = yt.search(query, limit=limit)
        except Exception:
            results = []
        for r in results:
            if r.get("resultType") in ("song", "video"):
                candidates.append(_to_candidate(r, is_music=_is_music(r)))

    return candidates


def _to_candidate(r, is_music):
    artists = ", ".join(a["name"] for a in r.get("artists", []) if a.get("name"))
    return {
        "videoId": r.get("videoId"),
        "title": r.get("title", ""),
        "artists": artists,
        "duration_sec": r.get("duration_seconds"),
        "is_music": is_music,
    }


def get_or_create_playlist(yt, name, description="Spotify'dan senkronize edildi"):
    """
    Verilen isimde playlist varsa id'sini dondur, yoksa olustur.
    Donen: (playlist_id, var_olan_mi)
    """
    existing = yt.get_library_playlists(limit=100)
    for pl in existing:
        if pl.get("title") == name:
            return pl["playlistId"], True
    # yoksa olustur
    return yt.create_playlist(name, description), False


def get_existing_track_keys(yt, playlist_id):
    """
    YouTube Music listesinde HALIHAZIRDA olan sarkilarin
    normalize edilmis (isim|sanatci) anahtarlarini bir kume olarak dondur.
    Bu sayede Spotify'da olup bu listede zaten var olan sarkilar
    icin tekrar arama YAPMAYIZ.
    """
    import matcher  # dairesel import olmamasi icin burada
    keys = set()
    try:
        pl = yt.get_playlist(playlist_id, limit=None)
    except Exception as e:
        print(f"  ! Mevcut liste okunamadi: {e}")
        return keys

    for track in pl.get("tracks", []):
        title = track.get("title", "") or ""
        artists = ", ".join(
            a["name"] for a in (track.get("artists") or []) if a.get("name")
        )
        key = matcher.track_key(title, artists)
        if key:
            keys.add(key)
    return keys


def add_to_playlist(yt, playlist_id, video_id, retries=2):
    """Bir sarkiyi playlist'e ekle.
    Donen: (ok, already_exists)
      ok=True  -> eklendi ya da zaten var (her iki durumda da basarili sayilir)
      already_exists=True -> sarki zaten listedeydi (409)
    409 Conflict = "zaten var" ya da gecici cakisma; basarili sayariz.
    Diger gecici hatalarda kisa bekleyip tekrar deneriz.
    """
    import time

    for attempt in range(retries + 1):
        try:
            resp = yt.add_playlist_items(playlist_id, [video_id], duplicates=False)
            status = resp.get("status", "") if isinstance(resp, dict) else ""
            # SADECE gercek basari basarili sayilir. Aksi halde sarki DB'ye
            # "synced" yazilip sessizce kaybolur (bir daha denenmez).
            if "SUCCEEDED" in status:
                return True, False
            # Basari degil: gecici olabilir, son deneme degilse tekrar dene.
            if attempt < retries:
                time.sleep(1.5)
                continue
            print(f"  ! Ekleme basarisiz (status={status!r})")
            return False, False
        except Exception as e:
            msg = str(e)
            # 409 = zaten var / cakisma -> basarili say
            if "409" in msg or "Conflict" in msg:
                return True, True
            # Son deneme degilse kisa bekle ve tekrar dene
            if attempt < retries:
                time.sleep(1.5)
                continue
            print(f"  ! Ekleme hatasi: {e}")
            return False, False
    return False, False


def remove_from_playlist(yt, playlist_id, video_id):
    """Bir videoyu playlist'ten sil. setVideoId gerektigi icin once
    listede o videoyu bulup setVideoId'sini almamiz gerekir.
    Basariliysa True."""
    try:
        pl = yt.get_playlist(playlist_id, limit=None)
    except Exception as e:
        print(f"  ! Liste okunamadi (silme icin): {e}")
        return False

    target = None
    for track in pl.get("tracks", []):
        if track.get("videoId") == video_id and track.get("setVideoId"):
            target = track
            break

    if not target:
        # Zaten listede yok sayilir; basarili kabul et
        return True

    try:
        yt.remove_playlist_items(playlist_id, [target])
        return True
    except Exception as e:
        print(f"  ! Silme hatasi: {e}")
        return False
