#!/usr/bin/env python3
# tallenna_pdf.py — purkaa PDF:n tekstin (pdftotext) ja tallentaa siitä suomenkielisen
# tiivistelmän (Mistral) tiedostoon /vault/Clippings/PDF-tiivistelmät/<otsikko>.md.
#
# Peilaa verkkosivuputkea (tallenna_verkkosivu.py): teksti → tiivistys → tallennus, samaan
# frontmatter-muotoon. Alkuperäistä sisältöä ei säilytetä; tiivistelmä on lopputuote, joten
# jos Mistral ei vastaa, tiedostoa ei luoda (PDF on yhä saatavilla uutta yritystä varten).
#
# Tekstin purku: pdftotext (poppler-utils). Kuvapohjaiset/skannatut PDF:t eivät tuota tekstiä
# -> niihin tarvitaan myöhemmin OCR (esim. Docling). Tämä versio käsittelee tekstipohjaiset.
#
# Käyttö:  tallenna_pdf.py <dokumentti.pdf | https://.../tiedosto.pdf>
#          URL:n tapauksessa PDF ladataan ja LÄHTEEKSI merkitään URL (ei paikallinen polku).

import os, re, subprocess, sys, tempfile, urllib.request
from datetime import date
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mistral_apu import kutsu_mistral, muotoile_tiivistelma, tiivistys_kehote
from tiedosto_apu import siisti_tiedostonimi
from verkko_apu import sivu_sallittu, UA

KANSIO = "/vault/Clippings/PDF-tiivistelmät"


def loki(viesti):
    print(viesti, flush=True)


def siisti_nimi(otsikko):
    return siisti_tiedostonimi(otsikko, oletus="dokumentti")


def pura_teksti(polku):
    # pdftotext annetusta PDF:stä stdoutiin. Palauttaa siistityn tekstin (tyhjä jos skannattu).
    try:
        tulos = subprocess.run(["pdftotext", "-enc", "UTF-8", polku, "-"],
                               capture_output=True, text=True, timeout=120)
    except FileNotFoundError:
        sys.exit("pdftotext puuttuu (asenna poppler-utils).")
    except subprocess.TimeoutExpired:
        sys.exit(f"pdftotext aikakatkaistiin: {polku}")
    if tulos.returncode != 0:
        sys.exit(f"pdftotext epäonnistui: {(tulos.stderr or '').strip()[:200]}")
    teksti = tulos.stdout.replace("\f", "\n")          # sivunvaihdot -> rivinvaihdot
    teksti = re.sub(r"[ \t]+", " ", teksti)
    teksti = re.sub(r"\n{3,}", "\n\n", teksti)
    return teksti.strip()


def jasenna_pdfinfo(teksti):
    # Poimii pdfinfon "Avain: arvo"-riveistä Title- ja Author-kentät.
    meta = {}
    for rivi in teksti.splitlines():
        if ":" in rivi:
            avain, _, arvo = rivi.partition(":")
            meta[avain.strip()] = arvo.strip()
    return {"otsikko": meta.get("Title", ""), "julkaisija": meta.get("Author", "")}


def hae_metatiedot(polku):
    try:
        tulos = subprocess.run(["pdfinfo", polku], capture_output=True, text=True, timeout=30)
        if tulos.returncode == 0:
            return jasenna_pdfinfo(tulos.stdout)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return {"otsikko": "", "julkaisija": ""}


def tiivista(teksti):
    try:
        return kutsu_mistral(tiivistys_kehote(teksti, "tämän PDF-dokumentin sisällöstä"))
    except Exception as e:
        loki(f"Mistral-kutsu epäonnistui: {e}")
        return ""


def lataa_pdf(url):
    # Lataa PDF:n URL:sta tilapäistiedostoon ja palauttaa sen polun. robots.txt
    # huomioidaan (verkko_apu). Varmistaa %PDF-tunnisteen ettei tallenneta HTML-virhesivua.
    if not sivu_sallittu(url):
        sys.exit(f"Lataus ei sallittu (robots.txt): {url}")
    try:
        pyynto = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(pyynto, timeout=60) as vastaus:
            data = vastaus.read(50_000_000)  # 50 MB raja
    except Exception as e:
        sys.exit(f"PDF:n lataus epäonnistui: {e}")
    if not data.startswith(b"%PDF"):
        sys.exit("Ladattu sisältö ei ole PDF (ei %PDF-tunnistetta).")
    fd, polku = tempfile.mkstemp(suffix=".pdf")
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    return polku


def main():
    if len(sys.argv) < 2:
        sys.exit("Käyttö: tallenna_pdf.py <dokumentti.pdf | url>")
    if sys.argv[1] == "--itsetesti":
        return _itsetesti()
    syote = sys.argv[1]

    # URL → lataa ja merkitse URL lähteeksi; polku → käytä polkua lähteenä.
    on_url = syote.startswith(("http://", "https://"))
    if on_url:
        lahde = syote
        polku = lataa_pdf(syote)
        oletus_otsikko = os.path.splitext(os.path.basename(urlparse(syote).path))[0]
    else:
        if not os.path.isfile(syote):
            sys.exit(f"Tiedostoa ei löydy: {syote}")
        if not syote.lower().endswith(".pdf"):
            sys.exit(f"Ei PDF-tiedosto: {syote}")
        lahde = syote
        polku = syote
        oletus_otsikko = os.path.splitext(os.path.basename(syote))[0]

    try:
        teksti = pura_teksti(polku)
        if not teksti:
            sys.exit("Ei tekstisisältöä (todennäköisesti skannattu PDF — vaatii OCR:n, esim. Docling).")
        tiivistelma = tiivista(teksti)
        if not tiivistelma:
            sys.exit("Tiivistys epäonnistui — tiedostoa ei luotu (yritä uudelleen).")

        meta = hae_metatiedot(polku)
        otsikko = meta["otsikko"] or oletus_otsikko or "dokumentti"
        julkaisija = meta["julkaisija"] or "PDF"
        uusi = muotoile_tiivistelma(otsikko, lahde, date.today().isoformat(), julkaisija, tiivistelma)

        os.makedirs(KANSIO, exist_ok=True)
        kohde = os.path.join(KANSIO, f"{siisti_nimi(otsikko)}.md")
        tmp = f"{kohde}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(uusi)
        os.replace(tmp, kohde)
        print(f"Saved to: {kohde}")
    finally:
        if on_url:
            try:
                os.remove(polku)
            except OSError:
                pass


def _itsetesti():
    info = ("Title:          Vuosikertomus 2025\n"
            "Author:         Sitra\n"
            "Pages:          42\n")
    m = jasenna_pdfinfo(info)
    assert m["otsikko"] == "Vuosikertomus 2025", m
    assert m["julkaisija"] == "Sitra", m
    assert jasenna_pdfinfo("Pages: 1") == {"otsikko": "", "julkaisija": ""}
    assert siisti_nimi("a/b:c?") == "a_b_c_"
    print("tallenna_pdf itsetesti OK")


if __name__ == "__main__":
    main()
