#!/usr/bin/env python3
# tallenna_verkkosivu.py — hakee verkkosivun, tiivistää sen suomeksi (Mistral) ja tallentaa
# tiivistelmän tiedostoon /vault/Clippings/Verkkosivutiivistelmät/<otsikko>.md.
#
# Tarkistaa ENSIN robots.txt:n: jos verkkokaavinta on kielletty, sivua ei haeta. Alkuperäistä
# sisältöä ei säilytetä — tiivistelmä on lopputuote, joten jos Mistral ei vastaa, tiedostoa ei
# luoda (sivu on uudelleenhaettavissa). Päivämäärä sivun julkaisupäivästä, fallback tähän päivään.
#
# Kaavinta jaetaan EU Digital Sovereignty -ominaisuuden kanssa (verkko_apu.py).
#
# Käyttö:  tallenna_verkkosivu.py <url>

import os, sys
from datetime import date
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mistral_apu import kutsu_mistral, muotoile_tiivistelma, tiivistys_kehote
from tiedosto_apu import siisti_tiedostonimi
from verkko_apu import (sivu_sallittu, hae_html, html_tekstiksi, etsi_otsikko,
                        etsi_julkaisija, etsi_julkaisupvm)

KANSIO = "/vault/Clippings/Verkkosivutiivistelmät"


def loki(viesti):
    print(viesti, flush=True)


def siisti_nimi(otsikko, url):
    return siisti_tiedostonimi(otsikko or urlparse(url).netloc, oletus="verkkosivu")


def tiivista(teksti):
    # Palauttaa tiivistelmän tai "" jos malli ei vastaa / avain puuttuu.
    try:
        return kutsu_mistral(tiivistys_kehote(teksti, "tämän verkkosivun sisällöstä"))
    except Exception as e:
        loki(f"Mistral-kutsu epäonnistui: {e}")
        return ""


def main():
    if len(sys.argv) < 2:
        sys.exit("Käyttö: tallenna_verkkosivu.py <url>")
    url = sys.argv[1]

    if not sivu_sallittu(url):
        sys.exit(f"Verkkokaavinta ei sallittu (robots.txt): {url}")

    html = hae_html(url)
    if not html:
        sys.exit(f"Sivun haku epäonnistui tai sisältö ei ole HTML:ää: {url}")
    sisalto = html_tekstiksi(html)
    if not sisalto:
        sys.exit(f"Ei tekstisisältöä: {url}")

    tiivistelma = tiivista(sisalto)
    if not tiivistelma:
        sys.exit("Tiivistys epäonnistui — tiedostoa ei luotu (yritä uudelleen).")

    otsikko = etsi_otsikko(html) or "Verkkosivu"
    iso = etsi_julkaisupvm(html)
    paivays = iso or date.today().isoformat()
    julkaisija = etsi_julkaisija(html, url)
    uusi = muotoile_tiivistelma(otsikko, url, paivays, julkaisija, tiivistelma)

    os.makedirs(KANSIO, exist_ok=True)
    polku = os.path.join(KANSIO, f"{siisti_nimi(otsikko, url)}.md")
    tmp = f"{polku}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(uusi)
    os.replace(tmp, polku)
    print(f"Saved to: {polku}")


if __name__ == "__main__":
    main()
