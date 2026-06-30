"""
Nauhoita oma äänesi VoxCPM2:n referenssiksi.
Käyttää macOS:n sisäänrakennettua mikrofonia.

Käyttö:
  python nauhoita_aani.py                  # oletus 8 sekuntia
  python nauhoita_aani.py --seconds 10     # 10 sekuntia
"""

import argparse
import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VOICES_DIR = os.path.join(SCRIPT_DIR, "voices")


def main():
    parser = argparse.ArgumentParser(description="Nauhoita referenssiääni")
    parser.add_argument("--seconds", type=int, default=8, help="Nauhoituksen kesto sekunneissa")
    args = parser.parse_args()

    os.makedirs(VOICES_DIR, exist_ok=True)

    # Kysy nimi äänelle
    name = input("Anna äänelle nimi (esim. anton): ").strip().lower()
    if not name:
        print("Nimi vaaditaan.")
        sys.exit(1)
    name = name.replace(" ", "_")
    output = os.path.join(VOICES_DIR, f"{name}.wav")

    print(f"\nNauhoitetaan {args.seconds} sekuntia, 16 kHz mono -> {output}")
    print("Puhu selkeasti ja tasaisesti, esim:")
    print('  "Hei, nimeni on [nimi]. Testaan tekoälyn puhesynteesiä omalla äänelläni."')
    print()
    input("Paina Enter kun olet valmis... ")
    print(f"NAUHOITUS KÄYNNISSÄ ({args.seconds}s)...")

    # macOS: kayta sox (rec) tai ffmpeg
    try:
        subprocess.run(
            ["rec", "-r", "16000", "-c", "1", "-b", "16", output,
             "trim", "0", str(args.seconds)],
            check=True,
        )
    except FileNotFoundError:
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-f", "avfoundation", "-i", ":0",
                 "-ac", "1", "-ar", "16000", "-t", str(args.seconds),
                 output],
                check=True,
            )
        except FileNotFoundError:
            print("\nTarvitset joko sox tai ffmpeg:")
            print("  brew install sox")
            print("  tai")
            print("  brew install ffmpeg")
            sys.exit(1)

    print(f"\nTallennettu: {output}")
    print(f"\nKäytä: aseta .env:hen VOXCPM_REFERENSSI={name}.wav")
    print(f"  (mactonuksen kommentointi/sano käyttää tätä ääntä voxcpm2_palvelin.py:n kautta)")


if __name__ == "__main__":
    main()
