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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from telegram_api import api_kutsu, laheta_viesti, riisu_markdown

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
SALLITUT = {c.strip() for c in os.environ.get("TELEGRAM_SALLITUT_CHATIT", "").split(",") if c.strip()}
PI_TYOHAKEMISTO = os.environ.get("PI_TYOHAKEMISTO", "/vault")
PI_AIKAKATKAISU = int(os.environ.get("PI_AIKAKATKAISU", "600"))
PI_MALLI = os.environ.get("PI_MALLI", "").strip()

# pi tallentaa sessiot tänne (yksi .jsonl per keskustelu). --session avaa vain
# olemassa olevan session, joten pidämme itse kirjaa per chat -> sessiopolku.
SESSIOT_JUURI = os.path.expanduser("~/.pi/agent/sessions")
SESSIO_KARTTA = os.path.expanduser("~/.pi/chats/sessiot.json")

# YouTube-linkin tunnistus viestistä. Jos linkki löytyy, silta lataa sen
# transkription deterministisesti download_transcript.sh:lla ENNEN kuin viesti
# menee pi:lle (ks. lataa_transkriptio). Polku selvitetään tämän tiedoston
# sijainnista, joten se toimii myös kontin ulkopuolella.
YOUTUBE_RE = re.compile(
    r"https?://(?:www\.|m\.)?(?:youtube\.com/(?:watch\?\S*v=|shorts/|live/)|youtu\.be/)[\w\-]+\S*"
)
LATAA_SKRIPTI = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "youtube", "download_transcript.sh",
)
LATAUS_AIKAKATKAISU = int(os.environ.get("YOUTUBE_AIKAKATKAISU", "180"))


def loki(viesti):
    print(viesti, flush=True)


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


def lataa_transkriptio(url):
    # Ajaa download_transcript.sh:n annetulla linkillä ja palauttaa luodun
    # transkriptiotiedoston polun, tai None jos lataus epäonnistui. Skripti
    # tulostaa onnistuessaan rivin "Saved to: <polku>".
    try:
        tulos = subprocess.run(
            ["bash", LATAA_SKRIPTI, url],
            cwd=PI_TYOHAKEMISTO,
            capture_output=True, text=True, timeout=LATAUS_AIKAKATKAISU,
        )
    except subprocess.TimeoutExpired:
        loki(f"Transkription lataus aikakatkaistiin: {url}")
        return None
    except FileNotFoundError:
        loki("Virhe: bash tai download_transcript.sh ei löydy.")
        return None
    for rivi in (tulos.stdout or "").splitlines():
        if rivi.startswith("Saved to:"):
            return rivi.split("Saved to:", 1)[1].strip()
    loki(f"Transkriptiota ei saatu ({url}): {(tulos.stdout or tulos.stderr or '').strip()[:200]}")
    return None


def esikasittele(teksti):
    # Jos viestissä on YouTube-linkki, ladataan sen transkriptio deterministisesti
    # ja kerrotaan pi:lle tiedostopolku (ei sisältöä -> ei konteksti- ikkunan
    # räjäytystä). Palauttaa pi:lle annettavan tekstin.
    osuma = YOUTUBE_RE.search(teksti)
    if not osuma:
        return teksti
    url = osuma.group(0)
    loki(f"YouTube-linkki havaittu, ladataan transkriptio: {url}")
    polku = lataa_transkriptio(url)
    if polku:
        ohje = (f"[Järjestelmä: viestin YouTube-video on jo litteroitu tiedostoon "
                f"{polku}. Lue se read-työkalulla, jos vastaus sitä edellyttää.]")
    else:
        ohje = ("[Järjestelmä: viestin YouTube-linkin litterointi epäonnistui — "
                "transkriptiota ei ole saatavilla.]")
    return f"{ohje}\n\n{teksti}"


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
                laheta_viesti(chat_id, "Ei käyttöoikeutta.", loki=loki)
                continue
            loki(f"Viesti {chat_id}: {teksti[:80]!r}")
            naytä_kirjoittaa(chat_id)
            teksti_pi = esikasittele(teksti)
            laheta_viesti(chat_id, riisu_markdown(aja_pi(chat_id, teksti_pi)), loki=loki)


if __name__ == "__main__":
    main()
