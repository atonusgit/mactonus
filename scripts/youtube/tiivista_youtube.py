#!/usr/bin/env python3
# tiivista_youtube.py — tuottaa suomenkielisen tiivistelmän YouTube-litteroinnista
# (Mistral-pilvimalli — litterointi on julkista dataa, ja pilvi on selvästi nopeampi
# kuin iso paikallinen malli) ja kirjoittaa tiedoston uusiksi muotoon: otsikko + lähde +
# tiivistelmä + litterointi samaan .md-tiedostoon.
#
# Kutsutaan download_transcript.sh:n lopussa annetulla litterointitiedostolla.
# Atominen kirjoitus: jos Mistral epäonnistuu, alkuperäinen litterointi jää ennalleen.
#
# Käyttö: tiivista_youtube.py /vault/Clippings/YouTube/<otsikko>.md

import os, sys

# mistral_apu.py ja config.py ovat scripts-juuressa
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mistral_apu import kutsu_mistral

# Litteroinnista syötetään enintään näin monta merkkiä mallille (kontekstiraja).
MAKS_LITTEROINTI = 16000


def jasenna(teksti):
    # download_transcript.sh:n muoto: "<header>\n\n---\n\n<litterointi>", missä header on
    # "# <otsikko>\n\nLähde: <url>\n<pvm-rivi>". Header säilytetään sellaisenaan (mm. pvm).
    if "\n---\n" in teksti:
        header, litterointi = teksti.split("\n---\n", 1)
        return header.strip(), litterointi.strip()
    return "", teksti.strip()


def main():
    if len(sys.argv) < 2:
        sys.exit("Käyttö: tiivista_youtube.py <litterointitiedosto.md>")
    polku = sys.argv[1]
    with open(polku, encoding="utf-8") as f:
        teksti = f.read()
    header, litterointi = jasenna(teksti)
    if not litterointi.strip():
        sys.exit("Ei litterointia tiivistettäväksi.")

    syote = litterointi[:MAKS_LITTEROINTI]
    katkaistu = len(litterointi) > MAKS_LITTEROINTI
    kehote = (
        "Tee suomenkielinen tiivistelmä tästä YouTube-videon litteroinnista. "
        "Aloita 2–3 lauseen yhteenvedolla, sitten tärkeimmät kohdat lyhyinä ranskalaisina "
        "viivoina. Litterointi voi olla englanniksi — tiivistä silti suomeksi. "
        "Älä keksi mitään, mitä litteroinnissa ei ole.\n\n"
        f"=== LITTEROINTI{' (katkaistu)' if katkaistu else ''} ===\n{syote}\n\n=== TIIVISTELMÄ ==="
    )
    try:
        tiivistelma = kutsu_mistral(kehote)
    except Exception as e:
        sys.exit(f"Mistral-kutsu epäonnistui: {e}")
    if not tiivistelma:
        sys.exit("Mistral ei palauttanut tiivistelmää.")

    osat = [header or "# YouTube-video", "",
            "## Tiivistelmä", "", tiivistelma, "",
            "## Litterointi", "", litterointi, ""]
    uusi = "\n".join(osat)

    tmp = f"{polku}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(uusi)
    os.replace(tmp, polku)
    print(f"Tiivistelmä lisätty: {polku}")


if __name__ == "__main__":
    main()
