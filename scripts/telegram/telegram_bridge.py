#!/usr/bin/env python3
# Telegram-silta pi-botille.
#
# pi:ssä ei ole hermesin kaltaista gateway-tilaa, joten tämä prosessi toimii
# siltana: kuuntelee Telegramia long-pollauksella ja ajaa jokaista viestiä
# varten pi:n headless-tilassa (`pi -p`). Keskustelukonteksti säilyy per chat
# `--session`-lipulla. Vastaus lähetetään takaisin Telegramiin.
#
# TURVA: pi voi ajaa bashia ja kirjoittaa /vault:iin, joten vain
# TELEGRAM_SALLITUT_CHATIT-listan chatit pääsevät läpi. Ilman listaa silta ei
# käynnisty.
#
# Ympäristömuuttujat (.env):
#   TELEGRAM_BOT_TOKEN        @BotFatherin antama token (pakollinen)
#   TELEGRAM_SALLITUT_CHATIT  sallitut chat-id:t pilkulla erotettuna (pakollinen)
#   PI_TYOHAKEMISTO           pi:n työhakemisto (oletus /vault)
#   PI_AIKAKATKAISU           yhden vastauksen aikaraja sekunteina (oletus 600)
#   PI_MALLI                  pakota malli `--model`-lipulla (oletus: tyhjä = pi
#                             valitsee models.json:n ainoan mallin)

import json, os, re, sys, time, glob, subprocess
import urllib.request, urllib.parse

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
SALLITUT = {c.strip() for c in os.environ.get("TELEGRAM_SALLITUT_CHATIT", "").split(",") if c.strip()}
PI_TYOHAKEMISTO = os.environ.get("PI_TYOHAKEMISTO", "/vault")
PI_AIKAKATKAISU = int(os.environ.get("PI_AIKAKATKAISU", "600"))
PI_MALLI = os.environ.get("PI_MALLI", "").strip()
API = f"https://api.telegram.org/bot{TOKEN}"

# pi tallentaa sessiot tänne (yksi .jsonl per keskustelu). --session avaa vain
# olemassa olevan session, joten pidämme itse kirjaa per chat -> sessiopolku.
SESSIOT_JUURI = os.path.expanduser("~/.pi/agent/sessions")
SESSIO_KARTTA = os.path.expanduser("~/.pi/chats/sessiot.json")


def loki(viesti):
    print(viesti, flush=True)


def api_kutsu(metodi, data=None, timeout=60):
    datab = urllib.parse.urlencode(data).encode() if data else None
    pyynto = urllib.request.Request(f"{API}/{metodi}", data=datab)
    with urllib.request.urlopen(pyynto, timeout=timeout) as vastaus:
        return json.load(vastaus)


def riisu_markdown(teksti):
    # Telegram ei renderöi markdownia ilman parse_mode-parametria, joten
    # poistetaan pi:n vastauksesta markdown-syntaksi ja jätetään pelkkä teksti.
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


def laheta_viesti(chat_id, teksti):
    # Telegram rajoittaa 4096 merkkiin -> paloitellaan turvallisesti.
    teksti = teksti or "(tyhjä vastaus)"
    for i in range(0, len(teksti), 4000):
        try:
            api_kutsu("sendMessage", {"chat_id": chat_id, "text": teksti[i:i + 4000]})
        except Exception as e:
            loki(f"Lähetys epäonnistui chatille {chat_id}: {e}")


def naytä_kirjoittaa(chat_id):
    try:
        api_kutsu("sendChatAction", {"chat_id": chat_id, "action": "typing"})
    except Exception:
        pass


def lataa_kartta():
    try:
        with open(SESSIO_KARTTA) as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {}


def tallenna_kartta(kartta):
    os.makedirs(os.path.dirname(SESSIO_KARTTA), exist_ok=True)
    with open(SESSIO_KARTTA, "w") as f:
        json.dump(kartta, f, ensure_ascii=False, indent=2)


def kaikki_sessiotiedostot():
    return set(glob.glob(os.path.join(SESSIOT_JUURI, "**", "*.jsonl"), recursive=True))


def aja_pi(chat_id, teksti):
    kartta = lataa_kartta()
    sessio = kartta.get(chat_id)
    jatketaan = bool(sessio) and os.path.exists(sessio)

    komento = ["pi", "-p"]
    if PI_MALLI:
        komento += ["--model", PI_MALLI]
    if jatketaan:
        # Jatka tämän chatin aiempaa keskustelua sessiopolun kautta.
        komento += ["--session", sessio]
    komento += [teksti]

    # Uutta sessiota luotaessa otetaan tilannekuva, jotta tunnistamme juuri
    # luodun .jsonl:n (silta käsittelee viestit yksitellen -> ei kilpailutilannetta).
    ennen = set() if jatketaan else kaikki_sessiotiedostot()
    try:
        tulos = subprocess.run(
            komento, cwd=PI_TYOHAKEMISTO,
            capture_output=True, text=True, timeout=PI_AIKAKATKAISU,
        )
    except subprocess.TimeoutExpired:
        return "Vastaus aikakatkaistiin (malli oli liian hidas)."
    except FileNotFoundError:
        return "Virhe: pi-komentoa ei löydy kontista."

    if not jatketaan:
        uudet = kaikki_sessiotiedostot() - ennen
        if uudet:
            kartta[chat_id] = max(uudet, key=os.path.getmtime)
            tallenna_kartta(kartta)
        else:
            loki(f"Varoitus: uutta sessiotiedostoa ei löytynyt chatille {chat_id}.")

    vastaus = (tulos.stdout or "").strip()
    if tulos.returncode != 0:
        virhe = (tulos.stderr or "").strip()
        loki(f"pi virhe (rc={tulos.returncode}): {virhe}")
        return vastaus or f"pi epäonnistui: {virhe[:500]}"
    return vastaus or "(pi ei palauttanut tekstiä)"


def main():
    if not TOKEN:
        sys.exit("TELEGRAM_BOT_TOKEN puuttuu .env:stä.")
    if not SALLITUT:
        sys.exit("TELEGRAM_SALLITUT_CHATIT puuttuu .env:stä (pakollinen turvasyistä).")
    loki(f"Telegram-silta käynnistyy. Sallitut chatit: {sorted(SALLITUT)}")

    # Tyhjennä backlog käynnistyksessä: ohita ennen käynnistystä tulleet viestit.
    offset = None
    try:
        alku = api_kutsu("getUpdates", {"timeout": 0})
        if alku.get("result"):
            offset = alku["result"][-1]["update_id"] + 1
    except Exception as e:
        loki(f"Backlogin tyhjennys epäonnistui: {e}")

    while True:
        try:
            data = {"timeout": 30}
            if offset is not None:
                data["offset"] = offset
            vastaus = api_kutsu("getUpdates", data, timeout=40)
        except Exception as e:
            loki(f"getUpdates epäonnistui: {e}")
            time.sleep(5)
            continue

        for upd in vastaus.get("result", []):
            offset = upd["update_id"] + 1
            viesti = upd.get("message") or upd.get("edited_message")
            if not viesti:
                continue
            chat_id = str(viesti.get("chat", {}).get("id", ""))
            teksti = viesti.get("text", "")
            if not teksti:
                continue
            if chat_id not in SALLITUT:
                loki(f"Estetty chat {chat_id}: {teksti[:50]!r}")
                laheta_viesti(chat_id, "Ei käyttöoikeutta.")
                continue
            loki(f"Viesti {chat_id}: {teksti[:80]!r}")
            naytä_kirjoittaa(chat_id)
            laheta_viesti(chat_id, riisu_markdown(aja_pi(chat_id, teksti)))


if __name__ == "__main__":
    main()
