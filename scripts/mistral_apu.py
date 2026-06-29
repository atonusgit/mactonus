#!/usr/bin/env python3
# mistral_apu.py — yhteinen Mistral-pilvikutsu. Käytetään YouTube-litterointien
# (tiivista_youtube.py) ja verkkosivujen (tallenna_verkkosivu.py) tiivistykseen.
# Asetukset config.py:stä. Nostaa RuntimeError:in jos avain puuttuu tai kutsu kaatuu,
# jotta kutsuja voi päättää (best-effort vs. lopeta) itse.

import json, os, sys, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import MISTRAL_MALLI, MISTRAL_URL, MISTRAL_API_KEY, MISTRAL_AIKAKATKAISU


def kutsu_mistral(kehote):
    if not MISTRAL_API_KEY:
        raise RuntimeError("MISTRAL_API_KEY puuttuu .env:stä.")
    data = json.dumps({"model": MISTRAL_MALLI,
                       "messages": [{"role": "user", "content": kehote}]}).encode("utf-8")
    pyynto = urllib.request.Request(MISTRAL_URL, data=data,
                                    headers={"Content-Type": "application/json",
                                             "Authorization": f"Bearer {MISTRAL_API_KEY}"})
    with urllib.request.urlopen(pyynto, timeout=MISTRAL_AIKAKATKAISU) as vastaus:
        viesti = json.load(vastaus)["choices"][0]["message"]["content"]
        return (viesti or "").strip()
