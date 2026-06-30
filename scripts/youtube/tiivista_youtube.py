#!/usr/bin/env python3
# tiivista_youtube.py — tuottaa suomenkielisen tiivistelmän YouTube-litteroinnista
# (Mistral-pilvimalli — litterointi on julkista dataa, ja pilvi on selvästi nopeampi kuin
# iso paikallinen malli) ja kirjoittaa tiedoston lopulliseen muotoon: frontmatter + tiivistelmä.
# Litterointia itseään ei säilytetä.
#
# Kutsutaan lataa_transkriptio.sh:n lopussa sen luomalla välitiedostolla, jonka muoto on:
#   "# <otsikko>\nLähde: <url>\nPäiväys: <pvm>\nJulkaisija: <kanava>\n\n---\n\n<litterointi>"
# Atominen kirjoitus: jos Mistral epäonnistuu, välitiedosto (litterointi) jää ennalleen.
#
# Käyttö: tiivista_youtube.py /vault/Clippings/YouTube/<otsikko>.md

import os, sys

# mistral_apu.py ja config.py ovat scripts-juuressa
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mistral_apu import kutsu_mistral, muotoile_tiivistelma, tiivistys_kehote


def jasenna(teksti):
    # Palauttaa (meta, litterointi). meta poimitaan header-lohkosta (ennen "---").
    header, litterointi = teksti.split("\n---\n", 1) if "\n---\n" in teksti else ("", teksti)
    meta = {"otsikko": "", "lahde": "", "paivays": "", "julkaisija": ""}
    for r in header.splitlines():
        r = r.strip()
        if r.startswith("# "):
            meta["otsikko"] = r[2:].strip()
        elif r.startswith("Lähde:"):
            meta["lahde"] = r.split(":", 1)[1].strip()
        elif r.startswith("Päiväys:"):
            meta["paivays"] = r.split(":", 1)[1].strip()
        elif r.startswith("Julkaisija:"):
            meta["julkaisija"] = r.split(":", 1)[1].strip()
    return meta, litterointi.strip()


def main():
    if len(sys.argv) < 2:
        sys.exit("Käyttö: tiivista_youtube.py <litterointitiedosto.md>")
    polku = sys.argv[1]
    with open(polku, encoding="utf-8") as f:
        teksti = f.read()
    meta, litterointi = jasenna(teksti)
    if not litterointi.strip():
        sys.exit("Ei litterointia tiivistettäväksi.")

    kehote = tiivistys_kehote(litterointi, "tämän YouTube-videon litteroinnista")
    try:
        tiivistelma = kutsu_mistral(kehote)
    except Exception as e:
        sys.exit(f"Mistral-kutsu epäonnistui: {e}")
    if not tiivistelma:
        sys.exit("Mistral ei palauttanut tiivistelmää.")

    uusi = muotoile_tiivistelma(meta["otsikko"] or "YouTube-video", meta["lahde"],
                                meta["paivays"], meta["julkaisija"] or "YouTube", tiivistelma)
    tmp = f"{polku}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(uusi)
    os.replace(tmp, polku)
    print(f"Tiivistelmä lisätty: {polku}")


if __name__ == "__main__":
    main()
