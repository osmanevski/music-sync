"""
YouTube Music icin browser authentication kurulumu.
OAuth'taki HTTP 400 sorunu nedeniyle bu yontemi kullaniyoruz.

Header'lari su sekillerde verebilirsin (script hepsini anlar):
  - Ham header blogu (Request Headers > Raw)
  - "Copy request headers" ciktisi
  - "Copy as cURL" ciktisi (script -H kisimlarini ayiklar)

KULLANIM:
  pbpaste | python setup_yt_browser.py        (panodan otomatik)
  python setup_yt_browser.py headers.txt      (dosyadan)

Header'lar terminale/sohbete dokulmeden dogrudan browser.json'a yazilir.
"""
import sys
import re
import ytmusicapi
import config


def extract_from_curl(text):
    """cURL ciktisindan header'lari ayikla.
    -H / --header satirlarini alir.
    Chrome cookie'yi bazen -b / --cookie bayraginda verir; onu da
    'cookie: ...' header'ina cevirir.
    """
    headers = []

    # -H 'x: y' ve --header 'x: y'
    for m in re.findall(r"""(?:-H|--header)\s+(['"])(.*?)\1""", text, re.DOTALL):
        headers.append(m[1])

    # -b 'deger' ve --cookie 'deger' -> cookie header'ina cevir
    cookie_match = re.search(r"""(?:-b|--cookie)\s+(['"])(.*?)\1""", text, re.DOTALL)
    if cookie_match:
        cookie_val = cookie_match.group(2)
        # Zaten bir cookie header'i yoksa ekle
        if not any(h.lower().startswith("cookie:") for h in headers):
            headers.append(f"cookie: {cookie_val}")

    if headers:
        return "\n".join(headers)
    return None


def main():
    if len(sys.argv) > 1:
        with open(sys.argv[1], "r") as f:
            raw = f.read()
    else:
        raw = sys.stdin.read()

    raw = raw.strip()
    if not raw:
        raise SystemExit(
            "Header bos. pbpaste ile pipe et ya da dosya yolu ver.\n"
            "Ornek: pbpaste | python setup_yt_browser.py"
        )

    # cURL ciktisi mi? Iceriyorsa header'lari ayikla.
    if raw.lstrip().startswith("curl") or "-H " in raw:
        extracted = extract_from_curl(raw)
        if extracted:
            raw = extracted

    ytmusicapi.setup(filepath=config.YT_BROWSER_FILE, headers_raw=raw)
    print(f"Tamam. '{config.YT_BROWSER_FILE}' olusturuldu.")


if __name__ == "__main__":
    main()
