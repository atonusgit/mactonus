#!/usr/bin/env python3
# tiedosto_apu.py — yhteinen tiedostonimien siistiminen. Korvaa VAIN tiedostojärjestelmässä
# / Obsidianissa oikeasti ongelmalliset merkit; ääkköset (ä ö å) ja muu Unicode säilyvät.
# Käyttäjät: youtube, verkkosivu, pdf, eu_digital_sovereignty, kuvat.
#
# (Aiemmin jokaisella oli oma valkolista [a-zA-Z0-9 _.,-], joka söi kaikki ääkköset _:ksi.)

import re

# Windowsin/eri alustojen kieltämät merkit + kontrollimerkit. Säilytetään mahd. siirrettävyys
# (vaultia voi synkata muillekin alustoille), siksi koko kielletty joukko eikä vain Unixin '/'.
_KIELLETYT = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def siisti_tiedostonimi(nimi, oletus="tiedosto", maks=120):
    nimi = _KIELLETYT.sub("_", nimi or "").strip()
    return (nimi or oletus)[:maks]


def _itsetesti():
    # Ääkköset säilyvät:
    assert siisti_tiedostonimi("Pörssisähkö ja käyttö") == "Pörssisähkö ja käyttö"
    assert siisti_tiedostonimi("Älä Öljyä") == "Älä Öljyä"
    # Kielletyt merkit -> _:
    assert siisti_tiedostonimi("a/b:c?*") == "a_b_c__", siisti_tiedostonimi("a/b:c?*")
    assert siisti_tiedostonimi('he"llo<x>') == "he_llo_x_"
    # Tyhjä -> oletus; pituusraja:
    assert siisti_tiedostonimi("") == "tiedosto"
    assert siisti_tiedostonimi("   ", oletus="x") == "x"
    assert siisti_tiedostonimi("ä" * 200, maks=10) == "ä" * 10
    print("tiedosto_apu itsetesti OK")


if __name__ == "__main__":
    _itsetesti()
