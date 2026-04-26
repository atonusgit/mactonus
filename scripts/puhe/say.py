#!/usr/bin/env python3
"""
VoxCPM2-client kontista. Lähettää tekstin hostin VoxCPM2-palvelimelle,
joka generoi ja soittaa hostin kaiuttimissa.

Vaatii että voxcpm2_server.py on käynnissä hostilla osoitteessa
host.docker.internal:8179.

Käyttö:
  python3 say.py "Hei maailma"
  python3 say.py --ref anton.wav "Hei"
  python3 say.py --voice "A deep male voice" "Hello"
  python3 say.py --no-play -o /vault/foo.wav "Vain tiedostoon"
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import VOXCPM_URL, VOXCPM_AIKAKATKAISU  # noqa: E402


def puhu(args):
    req = {
        "text": args.text,
        "ref": args.ref,
        "voice": args.voice,
        "play": not args.no_play,
        "output": args.output,
    }
    data = json.dumps(req).encode("utf-8")
    pyynto = urllib.request.Request(
        VOXCPM_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(pyynto, timeout=VOXCPM_AIKAKATKAISU) as vastaus:
            tulos = json.loads(vastaus.read().decode("utf-8"))
    except urllib.error.URLError as e:
        print(f"Yhteysvirhe: {e}. Onko voxcpm2_server.py käynnissä hostilla?", file=sys.stderr)
        return False

    if tulos.get("ok"):
        print(f"Tallennettu: {tulos['outfile']}")
        return True
    print(f"Virhe: {tulos.get('error')}", file=sys.stderr)
    return False


def main():
    parser = argparse.ArgumentParser(description="VoxCPM2-client kontille")
    parser.add_argument("text", help="Teksti joka puhutaan")
    parser.add_argument("--ref", default=None, help="Referenssi-wav (host-polku tai voices/-tiedostonimi)")
    parser.add_argument("--voice", default=None, help="Äänikuvaus")
    parser.add_argument("-o", "--output", default=None, help="Tallenna tiedostoon")
    parser.add_argument("--no-play", action="store_true", help="Älä soita, vain generoi")
    args = parser.parse_args()
    sys.exit(0 if puhu(args) else 1)


if __name__ == "__main__":
    main()
