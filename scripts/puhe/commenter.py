#!/usr/bin/env python3
"""Kommentoija — kuuntelee viimeisimmän nauhoitusistunnon litterointeja ja kommentoi ääneen.

Aja kontissa `comm`-aliaksella (docker exec). Vaatii:
  - Ollama hostilla (host.docker.internal:11434) ja MALLI_KOMMENTOIJA ladattuna
  - voxcpm2_server.py käynnissä hostilla (host.docker.internal:8179)
  - Vault-kehote tiedostossa /vault/mactonus/Kehotteet/Kommentoija.md
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import (  # noqa: E402
    MALLI_KOMMENTOIJA,
    OLLAMA_URL,
    OLLAMA_AIKAKATKAISU,
    VOXCPM_URL,
    VOXCPM_AIKAKATKAISU,
    VOXCPM_REFERENSSI,
    KOMMENTOIJA_KYNNYS,
)

VAULT = Path("/vault")
TMP_KANTA = VAULT / "mactonus" / "Nauhoitukset" / "tmp_chunks"
KEHOTE_POLKU = VAULT / "mactonus" / "Kehotteet" / "Kommentoija.md"

POLL_VALI = 3.0     # sekuntia
AKTIIVI_IKA = 300   # sek; istunto katsotaan aktiiviseksi jos .wav muokattu viimeksi tämän sisällä

SIISTIMIS_OHJE = (
    "Syöte on raakaa whisper-litterointia suomeksi useammasta peräkkäisestä äänipätkästä. "
    "Tulkitse ilmiselvät litterointivirheet sisäisesti, mutta tuota vastaus pelkän alla "
    "annetun kehotteen mukaisesti — älä erikseen siisti tai toista syötettä."
)


def ollama(systeemi: str, prompt: str) -> str:
    payload = json.dumps(
        {
            "model": MALLI_KOMMENTOIJA,
            "system": systeemi,
            "prompt": prompt,
            "stream": False,
        }
    ).encode("utf-8")
    pyynto = urllib.request.Request(
        OLLAMA_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(pyynto, timeout=OLLAMA_AIKAKATKAISU) as vastaus:
        data = json.loads(vastaus.read().decode("utf-8"))
    return data["response"].strip()


def viimeisin_aktiivinen_istunto() -> Path | None:
    if not TMP_KANTA.exists():
        return None
    nyt = time.time()
    ehdokkaat = []
    for kansio in TMP_KANTA.iterdir():
        if not kansio.is_dir():
            continue
        wavit = list(kansio.glob("*.wav"))
        if not wavit:
            continue
        tuorein_wav = max(w.stat().st_mtime for w in wavit)
        if nyt - tuorein_wav <= AKTIIVI_IKA:
            ehdokkaat.append((tuorein_wav, kansio))
    if not ehdokkaat:
        return None
    return max(ehdokkaat)[1]


def lue_kehote() -> str:
    if not KEHOTE_POLKU.exists():
        sys.exit(f"\033[1;31m✗ Kehotetta ei löydy: {KEHOTE_POLKU}\033[0m")
    teksti = KEHOTE_POLKU.read_text(encoding="utf-8").strip()
    if not teksti:
        sys.exit(f"\033[1;31m✗ Kehote on tyhjä: {KEHOTE_POLKU}\033[0m")
    return teksti


def puhu(teksti: str) -> None:
    payload = json.dumps(
        {"text": teksti, "ref": VOXCPM_REFERENSSI, "play": True}
    ).encode("utf-8")
    pyynto = urllib.request.Request(
        VOXCPM_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(pyynto, timeout=VOXCPM_AIKAKATKAISU) as vastaus:
            tulos = json.loads(vastaus.read().decode("utf-8"))
        if not tulos.get("ok"):
            print(f"\033[1;31m✗ VoxCPM2-virhe: {tulos.get('error')}\033[0m", file=sys.stderr)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace").strip()
        try:
            viesti = json.loads(body).get("error", body)
        except json.JSONDecodeError:
            viesti = body
        print(f"\033[1;31m✗ VoxCPM2-virhe ({e.code}): {viesti}\033[0m", file=sys.stderr)
    except urllib.error.URLError as e:
        print(
            f"\033[1;31m✗ VoxCPM2-yhteysvirhe: {e}. Onko voxcpm2_server.py käynnissä?\033[0m",
            file=sys.stderr,
        )


def main() -> None:
    kehote = lue_kehote()
    yhdistetty_kehote = f"{SIISTIMIS_OHJE}\n\n{kehote}"
    nykyinen: Path | None = None
    kasitellyt: set[str] = set()

    print("\033[1;32m● KOMMENTOIJA käynnissä\033[0m – Lopeta Ctrl+C")
    print(f"   Malli:    {MALLI_KOMMENTOIJA}")
    print(f"   Kynnys:   {KOMMENTOIJA_KYNNYS} uutta pätkää")
    print(f"   Kehote:   {KEHOTE_POLKU}")
    print(f"   VoxCPM2:  {VOXCPM_URL}")
    print()

    try:
        while True:
            istunto = viimeisin_aktiivinen_istunto()
            if istunto is None:
                time.sleep(POLL_VALI)
                continue

            if istunto != nykyinen:
                print(f"→ Seurataan istuntoa: {istunto.name}")
                nykyinen = istunto
                kasitellyt = set()

            txtit = sorted(
                p for p in istunto.glob("*.txt") if p.stat().st_size > 0
            )
            uudet = [t for t in txtit if t.name not in kasitellyt]

            if len(uudet) >= KOMMENTOIJA_KYNNYS:
                print(
                    f"⟳ Käsitellään {len(uudet)} pätkää: "
                    f"{', '.join(t.name for t in uudet)}"
                )
                raaka = "\n\n".join(
                    t.read_text(encoding="utf-8").strip() for t in uudet
                )
                try:
                    vastaus = ollama(yhdistetty_kehote, raaka)
                    print(f"\033[1;36m✎ {vastaus}\033[0m\n")
                    puhu(vastaus)
                    for t in uudet:
                        kasitellyt.add(t.name)
                except (OSError, KeyError, json.JSONDecodeError) as e:
                    print(f"\033[1;31m✗ Ollama-virhe: {e}\033[0m", file=sys.stderr)

            time.sleep(POLL_VALI)
    except KeyboardInterrupt:
        print("\nLopetetaan.")


if __name__ == "__main__":
    main()
