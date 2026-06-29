#!/usr/bin/env python3
# tallenna_verkkosivu.py — hakee verkkosivun, tiivistää sen suomeksi (Mistral) ja
# tallentaa tiedostoon /vault/Clippings/Verkkosivutiivistelmät/<otsikko>.md.
#
# Tarkistaa ENSIN robots.txt:n: jos verkkokaavinta on kielletty, sivua ei haeta. Best-effort
# tiivistys: jos Mistral ei vastaa (tai avain puuttuu), tiedosto tallennetaan silti pelkkänä
# sisältönä. Päivämäärä otetaan sivun julkaisupäivästä, tai jos sitä ei löydy, tallennuspäivästä.
#
# Kaavinta jaetaan EU Digital Sovereignty -ominaisuuden kanssa (verkko_apu.py).
#
# Käyttö:  tallenna_verkkosivu.py <url>

import os, re, sys
from datetime import date
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mistral_apu import kutsu_mistral
from verkko_apu import sivu_sallittu, hae_html, html_tekstiksi, etsi_otsikko, etsi_julkaisupvm

KANSIO = "/vault/Clippings/Verkkosivutiivistelmät"
# Sisällöstä syötetään enintään näin monta merkkiä mallille (kontekstiraja).
MAKS_SISALTO = 16000


def loki(viesti):
    print(viesti, flush=True)


def siisti_nimi(otsikko, url):
    nimi = otsikko or urlparse(url).netloc or "verkkosivu"
    nimi = re.sub(r"[^a-zA-Z0-9 _.,-]", "_", nimi).strip()
    return (nimi or "verkkosivu")[:120]


def tiivista(teksti):
    # Best-effort: palauttaa tiivistelmän tai "" jos malli ei vastaa / avain puuttuu.
    syote = teksti[:MAKS_SISALTO]
    katkaistu = len(teksti) > MAKS_SISALTO
    kehote = (
        "Tee suomenkielinen tiivistelmä tästä verkkosivun sisällöstä. "
        "Aloita 2–3 lauseen yhteenvedolla, sitten tärkeimmät kohdat lyhyinä ranskalaisina "
        "viivoina. Sisältö voi olla englanniksi — tiivistä silti suomeksi. "
        "Älä keksi mitään, mitä sisällössä ei ole.\n\n"
        f"=== SISÄLTÖ{' (katkaistu)' if katkaistu else ''} ===\n{syote}\n\n=== TIIVISTELMÄ ==="
    )
    try:
        return kutsu_mistral(kehote)
    except Exception as e:
        loki(f"Tiivistys ohitettiin (Mistral ei vastannut: {e}).")
        return ""


def kirjoita(polku, otsikko, url, pvm_rivi, tiivistelma, sisalto):
    osat = [f"# {otsikko}" if otsikko else "# Verkkosivu", "", f"Lähde: {url}", pvm_rivi, ""]
    if tiivistelma:
        osat += ["## Tiivistelmä", "", tiivistelma, ""]
    osat += ["## Sisältö", "", sisalto, ""]
    tmp = f"{polku}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(osat))
    os.replace(tmp, polku)


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

    otsikko = etsi_otsikko(html)
    iso = etsi_julkaisupvm(html)
    pvm_rivi = f"Julkaistu: {iso}" if iso else f"Tallennettu: {date.today().isoformat()}"
    tiivistelma = tiivista(sisalto)

    os.makedirs(KANSIO, exist_ok=True)
    polku = os.path.join(KANSIO, f"{siisti_nimi(otsikko, url)}.md")
    kirjoita(polku, otsikko, url, pvm_rivi, tiivistelma, sisalto)
    print(f"Saved to: {polku}")


if __name__ == "__main__":
    main()
