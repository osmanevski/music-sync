"""
Eslestirme mantigi.

Bir Spotify sarkisi ile YouTube Music arama sonuclarini karsilastirir.
Uc kritere bakar:
  1. Sarki adi benzerligi
  2. Sanatci adi benzerligi
  3. Sure farki (saniye)

Her aday icin 0-100 arasi bir skor uretir. En yuksek skorlu aday secilir.
Skor MIN_CONFIDENCE_SCORE altindaysa "supheli" sayilir.
"""
import re
from difflib import SequenceMatcher
import config


def normalize(text):
    """Karsilastirma icin metni sadelestir: kucuk harf, parantez/feat temizligi."""
    if not text:
        return ""
    text = text.lower()
    # (feat. ...), (official video), [remastered] gibi parantezli ekleri at
    text = re.sub(r"[\(\[].*?[\)\]]", " ", text)
    # feat/ft sonrasi gelen ismi de at (parantezsiz "feat. X" durumu)
    text = re.sub(r"\b(feat|ft|featuring)\b.*$", " ", text)
    text = re.sub(r"\b(official|video|audio|lyrics?|remaster(ed)?)\b", " ", text)
    text = re.sub(r"[^\w\s]", " ", text)        # noktalama
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_artist(artist):
    """
    Sanatci adini ozel olarak normallestir.
    YouTube Music sik sik "- Topic" eki koyar (Tarkan -> "Tarkan - Topic").
    Ayrica "VEVO", "Official" gibi ekler olabilir.
    """
    if not artist:
        return ""
    a = artist.lower()
    # "- topic", "vevo", "official" eklerini temizle
    a = re.sub(r"\s*-\s*topic\s*$", "", a)
    a = re.sub(r"\bvevo\b", " ", a)
    a = re.sub(r"\bofficial\b", " ", a)
    # normalize'in geri kalanini uygula
    a = re.sub(r"[\(\[].*?[\)\]]", " ", a)
    a = re.sub(r"[^\w\s]", " ", a)
    a = re.sub(r"\s+", " ", a).strip()
    return a


def track_key(name, artists):
    """
    Bir sarkiyi YouTube ve Spotify arasinda karsilastirmak icin
    normalize edilmis anahtar uretir: "isim|ilk_sanatci".
    Sadece ilk sanatciyi kullaniriz cunku iki platform feat/sanatci
    listesini farkli yazabiliyor; ilk sanatci en guvenilir ortak nokta.
    Bosluklar tamamen kaldirilir ki "oynarmisin" = "oynar misin" olsun.
    "- Topic" gibi YouTube ekleri sanatci normalize'inde temizlenir.
    """
    n = normalize(name).replace(" ", "")
    first_artist = artists.split(",")[0] if artists else ""
    a = normalize_artist(first_artist).replace(" ", "")
    if not n:
        return ""
    return f"{n}|{a}"


def similarity(a, b):
    """Iki metin arasi 0-1 benzerlik."""
    return SequenceMatcher(None, normalize(a), normalize(b)).ratio()


def score_candidate(sp_track, yt_candidate):
    """
    sp_track: {name, artists, duration_sec}
    yt_candidate: {title, artists, duration_sec, videoId, is_music}
    Donen: 0-100 skor
    """
    name_sim = similarity(sp_track["name"], yt_candidate["title"])
    artist_sim = similarity(sp_track["artists"], yt_candidate["artists"])

    # Sure farki skoru
    dur_diff = abs(sp_track["duration_sec"] - (yt_candidate["duration_sec"] or 0))
    if dur_diff <= config.DURATION_TOLERANCE_SEC:
        dur_score = 1.0
    elif dur_diff <= 15:
        dur_score = 0.5
    else:
        dur_score = 0.0

    # Agirliklar: isim %40, sanatci %35, sure %25
    score = (name_sim * 0.40 + artist_sim * 0.35 + dur_score * 0.25) * 100

    # Muzik degil de video ise ceza ver (videoyu istemiyoruz)
    if not yt_candidate.get("is_music", True):
        score -= 20

    return round(score, 1)


def best_match(sp_track, yt_candidates):
    """
    En iyi adayi ve skorunu dondur.
    Donen: (best_candidate, score, all_scored)
    Aday yoksa (None, 0, []).
    """
    if not yt_candidates:
        return None, 0, []
    scored = []
    for c in yt_candidates:
        scored.append((c, score_candidate(sp_track, c)))
    scored.sort(key=lambda x: x[1], reverse=True)
    best, score = scored[0]
    return best, score, scored
