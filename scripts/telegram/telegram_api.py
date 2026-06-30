#!/usr/bin/env python3
# Telegram-API:n jaetut apurit. Käyttäjät: telegram_silta.py (saapuvat viestit)
# ja laheta.py (lähtevät viestit cron-jobeista).
#
# Token luetaan ympäristömuuttujasta TELEGRAM_BOT_TOKEN joka kutsulla, jotta
# sama koodi toimii sekä sillalle (token tulee konttiympäristöstä) että
# cron-jobeille (token periytetään kontin pääprosessilta, ks.
# peri_kontin_ymparisto — cron ei peri konttiympäristöä).

import json, os, re
import urllib.request, urllib.parse


def peri_kontin_ymparisto(pid=1):
    # Cron riisuu jobeilta ympäristön. Sen sijaan että kirjoittaisimme
    # salaisuudet levylle, luetaan ne takaisin kontin pääprosessin (PID 1)
    # ympäristöstä /proc:ista — tämä on kernelin pitämä prosessin ympäristö,
    # ei levylle syntyvä tiedosto. Olemassa olevia arvoja ei ylikirjoiteta.
    try:
        with open(f"/proc/{pid}/environ", "rb") as f:
            data = f.read()
    except OSError:
        # /proc puuttuu / ei lukuoikeutta -> jatketaan; arvot tulevat suoraan
        # ympäristöstä tai puuttuva token raportoidaan selkeästi myöhemmin.
        return
    for pari in data.split(b"\0"):
        if not pari or b"=" not in pari:
            continue
        avain, _, arvo = pari.partition(b"=")
        try:
            os.environ.setdefault(avain.decode(), arvo.decode())
        except UnicodeDecodeError:
            continue


def _api():
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    return f"https://api.telegram.org/bot{token}"


def api_kutsu(metodi, data=None, timeout=60):
    datab = urllib.parse.urlencode(data).encode() if data else None
    pyynto = urllib.request.Request(f"{_api()}/{metodi}", data=datab)
    with urllib.request.urlopen(pyynto, timeout=timeout) as vastaus:
        return json.load(vastaus)


def riisu_markdown(teksti):
    # Telegram ei renderöi markdownia ilman parse_mode-parametria, joten
    # poistetaan vastauksesta markdown-syntaksi ja jätetään pelkkä teksti.
    if not teksti:
        return teksti
    teksti = re.sub(r"```[\w-]*\n?", "", teksti)                  # koodiaidat pois
    teksti = re.sub(r"`([^`]+)`", r"\1", teksti)                  # `inline` -> inline
    teksti = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", teksti)         # ## otsikko -> otsikko
    teksti = re.sub(r"(\*\*|__)(.+?)\1", r"\2", teksti)           # **liha** -> liha
    teksti = re.sub(r"(?<!\w)([*_])(.+?)\1(?!\w)", r"\2", teksti) # *kursiivi* -> kursiivi
    teksti = re.sub(r"(?m)^(\s*)[-*+]\s+", r"\1• ", teksti)       # lista -> •
    teksti = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", teksti)  # [teksti](url) -> teksti (url)
    teksti = re.sub(r"(?m)^\s{0,3}>\s?", "", teksti)              # > lainaus pois
    return teksti


def laheta_viesti(chat_id, teksti, loki=print, parse_mode=None):
    # Telegram rajoittaa 4096 merkkiin -> paloitellaan turvallisesti.
    # parse_mode (esim. "HTML") mahdollistaa muotoilun, kuten <code>monospace</code>.
    # Oletus None = pelkkä teksti (entinen käyttäytyminen).
    teksti = teksti or "(tyhjä vastaus)"
    for i in range(0, len(teksti), 4000):
        data = {"chat_id": chat_id, "text": teksti[i:i + 4000]}
        if parse_mode:
            data["parse_mode"] = parse_mode
        try:
            api_kutsu("sendMessage", data)
        except Exception as e:
            loki(f"Lähetys epäonnistui chatille {chat_id}: {e}")
