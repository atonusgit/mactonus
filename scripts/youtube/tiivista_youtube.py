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

import json, os, sys, urllib.request

# config.py on scripts-juuressa
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import MISTRAL_MALLI, MISTRAL_URL, MISTRAL_API_KEY, MISTRAL_AIKAKATKAISU

# Litteroinnista syötetään enintään näin monta merkkiä Ollamalle (kontekstiraja).
MAKS_LITTEROINTI = 16000


def kutsu_mistral(kehote):
    if not MISTRAL_API_KEY:
        sys.exit("MISTRAL_API_KEY puuttuu .env:stä.")
    data = json.dumps({"model": MISTRAL_MALLI,
                       "messages": [{"role": "user", "content": kehote}]}).encode("utf-8")
    pyynto = urllib.request.Request(MISTRAL_URL, data=data,
                                    headers={"Content-Type": "application/json",
                                             "Authorization": f"Bearer {MISTRAL_API_KEY}"})
    with urllib.request.urlopen(pyynto, timeout=MISTRAL_AIKAKATKAISU) as vastaus:
        viesti = json.load(vastaus)["choices"][0]["message"]["content"]
        return (viesti or "").strip()


def jasenna(teksti):
    # download_transcript.sh:n muoto: "# <otsikko>\n\nLähde: <url>\n\n---\n\n<litterointi>".
    otsikko, url, litterointi = "", "", teksti
    rivit = teksti.splitlines()
    for r in rivit:
        if r.startswith("# ") and not otsikko:
            otsikko = r[2:].strip()
        elif r.startswith("Lähde:") and not url:
            url = r.split("Lähde:", 1)[1].strip()
    if "\n---\n" in teksti:
        litterointi = teksti.split("\n---\n", 1)[1].strip()
    return otsikko, url, litterointi


def main():
    if len(sys.argv) < 2:
        sys.exit("Käyttö: tiivista_youtube.py <litterointitiedosto.md>")
    polku = sys.argv[1]
    with open(polku, encoding="utf-8") as f:
        teksti = f.read()
    otsikko, url, litterointi = jasenna(teksti)
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
    tiivistelma = kutsu_mistral(kehote)
    if not tiivistelma:
        sys.exit("Ollama ei palauttanut tiivistelmää.")

    osat = [f"# {otsikko}" if otsikko else "# YouTube-video", ""]
    if url:
        osat += [f"Lähde: {url}", ""]
    osat += ["## Tiivistelmä", "", tiivistelma, "", "## Litterointi", "", litterointi, ""]
    uusi = "\n".join(osat)

    tmp = f"{polku}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(uusi)
    os.replace(tmp, polku)
    print(f"Tiivistelmä lisätty: {polku}")


if __name__ == "__main__":
    main()
