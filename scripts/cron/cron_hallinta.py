#!/usr/bin/env python3
# cron_hallinta.py — ajastusprimitiivi: luo/listaa/poista cron-ajoja oikealla
# /etc/cron.d-notaatiolla. Sekä `cron`-skill että `aihe-seuraaja` käyttävät tätä.
#
# /etc/cron.d -säännöt, jotka tämä hoitaa puolestasi:
#  - tiedostonimessä vain [A-Za-z0-9_-] (ei pistettä, muuten cron ohittaa sen)
#  - rivimuoto "<aikataulu> <käyttäjä> <komento>"
#  - PATH kannattaa asettaa, koska cron-ympäristö on riisuttu
#
# Käyttö:
#   cron_hallinta.py luo --nimi <nimi> --aikataulu "0 9 * * *" --komento "<komento>" [--loki <polku>]
#   cron_hallinta.py listaa
#   cron_hallinta.py poista --nimi <nimi>

import argparse, glob, os, re, sys

CRON_DIR = "/etc/cron.d"
LOKI_OLETUS_DIR = "/tmp/cron"
# Prefiksi erottaa skillin luomat cron-tiedostot järjestelmän omista (esim.
# analyze_images), jotta listaus/poisto eivät koske käsin tehtyihin ajoihin.
PREFIX = "aj_"
PATH_RIVI = "PATH=/usr/local/bin:/usr/local/sbin:/usr/bin:/sbin:/bin"

NIMI_RE = re.compile(r"^[a-z0-9_-]+$")


def _tarkista_nimi(nimi):
    if not NIMI_RE.match(nimi or ""):
        raise ValueError(
            f"Virheellinen nimi {nimi!r}: salli vain a-z, 0-9, _ ja - (ei pistettä).")


def _tarkista_aikataulu(aikataulu):
    kentat = (aikataulu or "").split()
    if len(kentat) != 5:
        raise ValueError(
            "Aikataulussa pitää olla 5 kenttää (min tunti pvm kk viikonpäivä), "
            f"sai {len(kentat)}: {aikataulu!r}")


def _polku(nimi):
    return os.path.join(CRON_DIR, f"{PREFIX}{nimi}")


def luo_ajastus(nimi, aikataulu, komento, loki=None):
    # Kirjoittaa cron-tiedoston. Palauttaa tiedostopolun. Importattava aihe-seuraajalle.
    _tarkista_nimi(nimi)
    _tarkista_aikataulu(aikataulu)
    if not (komento or "").strip():
        raise ValueError("Komento puuttuu.")
    if loki is None:
        loki = os.path.join(LOKI_OLETUS_DIR, f"{nimi}.log")
    os.makedirs(os.path.dirname(loki), exist_ok=True)
    os.makedirs(CRON_DIR, exist_ok=True)
    sisalto = f"{PATH_RIVI}\n{aikataulu} root {komento} >> {loki} 2>&1\n"
    polku = _polku(nimi)
    with open(polku, "w", encoding="utf-8") as f:
        f.write(sisalto)
    os.chmod(polku, 0o644)
    return polku


def poista_ajastus(nimi):
    _tarkista_nimi(nimi)
    polku = _polku(nimi)
    if os.path.exists(polku):
        os.remove(polku)
        return True
    return False


def listaa_ajastukset():
    # Palauttaa listan (nimi, aikataulu, komento) skillin luomista cron-ajoista.
    tulos = []
    for polku in sorted(glob.glob(os.path.join(CRON_DIR, f"{PREFIX}*"))):
        nimi = os.path.basename(polku)[len(PREFIX):]
        aikataulu, komento = "", ""
        try:
            for rivi in open(polku, encoding="utf-8"):
                rivi = rivi.strip()
                if not rivi or rivi.startswith("PATH=") or rivi.startswith("#"):
                    continue
                osat = rivi.split(None, 6)  # 5 aikataulukenttää + käyttäjä + komento
                if len(osat) >= 7:
                    aikataulu = " ".join(osat[:5])
                    komento = osat[6].split(" >> ")[0]  # piilota lokin uudelleenohjaus
                break
        except OSError:
            pass
        tulos.append((nimi, aikataulu, komento))
    return tulos


def main():
    p = argparse.ArgumentParser(description="Hallitse skillin luomia cron-ajoja.")
    ali = p.add_subparsers(dest="komento", required=True)

    pl = ali.add_parser("luo", help="Luo cron-ajastus.")
    pl.add_argument("--nimi", required=True)
    pl.add_argument("--aikataulu", required=True, help='5-kenttäinen cron, esim. "0 9 * * *"')
    pl.add_argument("--komento", required=True, help="Ajettava komento.")
    pl.add_argument("--loki", help="Lokitiedoston polku (oletus /tmp/cron/<nimi>.log).")

    ali.add_parser("listaa", help="Listaa ajastukset.")

    pp = ali.add_parser("poista", help="Poista ajastus.")
    pp.add_argument("--nimi", required=True)

    a = p.parse_args()
    try:
        if a.komento == "luo":
            polku = luo_ajastus(a.nimi, a.aikataulu, a.komento, a.loki)
            print(f"Ajastus luotu: {polku}")
        elif a.komento == "listaa":
            rivit = listaa_ajastukset()
            if not rivit:
                print("(ei ajastuksia)")
            for nimi, aikataulu, komento in rivit:
                print(f"- {nimi}: [{aikataulu}] {komento}")
        elif a.komento == "poista":
            print(f"Poistettu ajastus: {a.nimi}" if poista_ajastus(a.nimi)
                  else f"Ei löytynyt ajastusta: {a.nimi}")
    except ValueError as e:
        sys.exit(f"Virhe: {e}")


if __name__ == "__main__":
    main()
