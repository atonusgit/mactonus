#!/usr/bin/env python3
# verkko_apu.py — yhteinen verkkosivun kaavinta: robots.txt-tarkistus, sivun haku,
# HTML->teksti, otsikon ja julkaisupäivän kaivuu. Käyttäjät:
#   - eu_digital_sovereignty/paivittain.py  (Staan-uutisten sisällön luku)
#   - verkkosivu/tallenna_verkkosivu.py (linkin tallennus tiivistelmäksi)
# Pelkkää stdlibiä, ei uutta riippuvuutta.

import re
from html import unescape
from urllib.request import Request, urlopen
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

# Selaimen User-Agent: jotkin sivut torjuvat oletus-urllibin.
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def sivu_sallittu(url):
    # robots.txt: kunnioitetaan sivuston sääntöjä. Virhe / ei robots.txt:ää -> sallitaan
    # (lenient): käyttäjä antoi linkin tarkoituksella, vain eksplisiittistä Disallow:ia estetään.
    try:
        p = urlparse(url)
        robots = f"{p.scheme}://{p.netloc}/robots.txt"
        with urlopen(Request(robots, headers={"User-Agent": UA}), timeout=8) as r:
            rp = RobotFileParser()
            rp.parse(r.read().decode("utf-8", "replace").splitlines())
        return rp.can_fetch(UA, url)
    except Exception:
        return True


def hae_html(url, maks_tavua=2_000_000):
    # Hakee sivun raa'an HTML:n, tai None jos haku epäonnistuu tai sisältö ei ole HTML:ää.
    # EI tarkista robots.txt:ää — kutsuja vastaa siitä (ks. sivu_sallittu).
    try:
        pyynto = Request(url, headers={"User-Agent": UA, "Accept-Language": "fi,en;q=0.8"})
        with urlopen(pyynto, timeout=20) as resp:
            if "html" not in (resp.headers.get("Content-Type") or "").lower():
                return None
            raaka = resp.read(maks_tavua)
    except Exception:
        return None
    return raaka.decode("utf-8", "replace")


def html_tekstiksi(html, maks=None):
    # Purkaa HTML:stä pelkän tekstin (script/style/kommentit/tagit pois). Lohkotagit
    # muunnetaan rivinvaihdoiksi, jotta kappalerakenne säilyy. Palauttaa None jos tyhjä.
    html = re.sub(r"(?is)<(script|style|noscript|template)\b.*?</\1>", " ", html)
    html = re.sub(r"(?s)<!--.*?-->", " ", html)
    html = re.sub(r"(?i)</(p|div|li|h[1-6]|tr|section|article|header|footer)\s*>", "\n", html)
    html = re.sub(r"(?i)<br\s*/?>", "\n", html)
    teksti = unescape(re.sub(r"(?s)<[^>]+>", " ", html))
    teksti = re.sub(r"[ \t]+", " ", teksti)
    teksti = re.sub(r" *\n *", "\n", teksti)
    teksti = re.sub(r"\n{3,}", "\n\n", teksti).strip()
    return (teksti[:maks] if maks else teksti) or None


def etsi_otsikko(html):
    m = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
    return re.sub(r"\s+", " ", unescape(m.group(1))).strip() if m else ""


def etsi_julkaisija(html, url):
    # Julkaisija og:site_name-metasta; fallback verkkotunnukseen (www. pois).
    m = re.search(r'<meta[^>]+property=["\']og:site_name["\'][^>]+content=["\']([^"\']+)["\']', html, re.I)
    if not m:
        m = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:site_name["\']', html, re.I)
    if m:
        return unescape(m.group(1)).strip()
    return re.sub(r"^www\.", "", urlparse(url).netloc)


def etsi_julkaisupvm(html):
    # Kaivaa artikkelin julkaisupäivän (JSON-LD datePublished, meta-tagit, <time datetime>).
    # Palauttaa ISO-muodon "YYYY-MM-DD", tai None jos ei löydy.
    ehdokkaat = re.findall(r'"datePublished"\s*:\s*"([^"]+)"', html)
    nimet = r"article:published_time|datePublished|date|dc\.date|dcterms\.date|pubdate"
    ehdokkaat += re.findall(
        rf'<meta[^>]+(?:property|name|itemprop)=["\'](?:{nimet})["\'][^>]+content=["\']([^"\']+)["\']',
        html, re.I)
    ehdokkaat += re.findall(  # content ennen property/name -järjestys
        rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name|itemprop)=["\'](?:{nimet})["\']',
        html, re.I)
    ehdokkaat += re.findall(r'<time[^>]+datetime=["\']([^"\']+)["\']', html, re.I)
    for s in ehdokkaat:
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
        if m:
            return "-".join(m.groups())
    return None


def _itsetesti():
    html = (
        '<html><head><title> Otsikko\nrivillä </title>'
        '<meta property="article:published_time" content="2026-06-29T08:00:00Z">'
        '<style>.a{color:red}</style></head><body>'
        '<script>roska();</script><p>Eka kappale.</p><div>Toka osa</div></body></html>'
    )
    assert etsi_otsikko(html) == "Otsikko rivillä", repr(etsi_otsikko(html))
    teksti = html_tekstiksi(html)
    assert "Eka kappale." in teksti and "Toka osa" in teksti, repr(teksti)
    assert "roska" not in teksti and "color:red" not in teksti, repr(teksti)
    assert "\n" in teksti, "kappalerakenne pitäisi säilyä"
    assert etsi_julkaisupvm(html) == "2026-06-29", repr(etsi_julkaisupvm(html))
    assert etsi_julkaisupvm("<html></html>") is None
    htmlj = '<meta property="og:site_name" content="Yle">'
    assert etsi_julkaisija(htmlj, "https://yle.fi/x") == "Yle"
    assert etsi_julkaisija("", "https://www.example.com/a") == "example.com"
    print("verkko_apu itsetesti OK")


if __name__ == "__main__":
    _itsetesti()
