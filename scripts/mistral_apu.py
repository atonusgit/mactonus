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


def tiivistys_kehote(sisalto, lahdetyyppi, maks=16000):
    # Rakentaa kehotteen jäsennellylle, yksityiskohtia säilyttävälle tiivistelmälle.
    # lahdetyyppi esim. "tämän YouTube-videon litteroinnista" / "tämän verkkosivun sisällöstä".
    syote = sisalto[:maks]
    katkaistu = len(sisalto) > maks
    return (
        f"Tee tiivis, jäsennelty suomenkielinen tiivistelmä {lahdetyyppi}. "
        "Pidä se LYHYENÄ — vain olennainen, ei toistoa eikä täytettä. "
        "Käytä Markdownia ja noudata tätä rakennetta:\n"
        "- Aloita \"## Ydinlöydös\" -osiolla: 2–3 lausetta tärkeimmästä asiasta.\n"
        "- Tarvittaessa muutama lyhyt aihekohtainen \"##\"-osio, kukin parilla ranskalaisella "
        "viivalla.\n"
        "- Säilytä tärkeimmät konkreettiset luvut, asetukset ja komennot; komennot ja koodi "
        "Markdown-koodilohkoissa.\n"
        "- Vertailudata saa olla Markdown-taulukkona. TÄRKEÄÄ: taulukon JA koodilohkon on "
        "alettava rivin vasemmasta reunasta omana kappaleenaan — EI koskaan sisennettynä "
        "luettelokohdan alle, sillä sisennetty taulukko ei renderöidy Obsidianissa. "
        "Jos haluat liittää taulukon johonkin kohtaan, tee se omana \"##\"-osionaan, älä "
        "ranskalaisen viivan alle.\n"
        "- Päätä \"## Keskeiset johtopäätökset\" -osioon lyhyenä numeroituna listana.\n"
        "Älä toista otsikkoa äläkä keksi mitään mitä sisällössä ei ole.\n\n"
        f"=== SISÄLTÖ{' (katkaistu)' if katkaistu else ''} ===\n{syote}\n\n=== TIIVISTELMÄ ==="
    )


def muotoile_tiivistelma(otsikko, lahde, paivays, julkaisija, tiivistelma):
    # Yhteinen lopullinen muoto YouTube- ja verkkosivutiivistelmille: frontmatter +
    # "# <otsikko> -tiivistelmä" + tiivistelmä. Alkuperäistä sisältöä ei säilytetä.
    return "\n".join([
        "---",
        f"Lähde: {lahde}",
        f"Päiväys: {paivays}",
        f"Julkaisija: {julkaisija}",
        "---",
        "",
        f"# {otsikko} -tiivistelmä",
        "",
        tiivistelma,
        "",
    ])
