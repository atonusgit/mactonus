#!/usr/bin/env python3
# seuraaja.py — aiheen seuranta ajassa. Ajastus hoidetaan cron_hallinta-skriptillä;
# cron ajaa "seuraaja.py aja <nimi>", joka:
#   1) ajaa pi:n headless-tilassa aiheen kehotteella (pi käyttää itse staan-web-searchia),
#   2) vertaa tulosta aiempiin (historia) ja
#   3) lähettää tiiviin päivityksen Telegramiin.
#
# Käyttö:
#   seuraaja.py luo --nimi <nimi> --aikataulu "0 9 * * *" --aihe "<mitä seurataan>" [--chat <id>]
#   seuraaja.py listaa
#   seuraaja.py poista --nimi <nimi>
#   seuraaja.py aja <nimi>          # cronin sisääntulopiste

import argparse, json, os, re, subprocess, sys
from datetime import datetime

PERUS = os.path.dirname(os.path.abspath(__file__))
AIHEET_DIR = os.path.join(PERUS, "aiheet")
HISTORIA_DIR = os.path.join(PERUS, "historia")
LOKI_DIR = "/tmp/aihe_seuraaja"
SCRIPTS_DIR = os.path.dirname(PERUS)                 # /root/scripts
TELEGRAM_DIR = os.path.join(SCRIPTS_DIR, "telegram")
CRON_DIR = os.path.join(SCRIPTS_DIR, "cron")

# Cronista ajettava sisääntulopiste (kontin absoluuttinen polku).
AJA_KOMENTO_MALLI = "python3 /root/scripts/aihe_seuraaja/seuraaja.py aja {nimi}"

PI_AIKAKATKAISU = int(os.environ.get("AIHE_SEURAAJA_AIKAKATKAISU", "600"))
HISTORIA_MAX = 5

sys.path.insert(0, CRON_DIR)
sys.path.insert(0, TELEGRAM_DIR)
import cron_hallinta
from telegram_api import peri_kontin_ymparisto

NIMI_RE = re.compile(r"^[a-z0-9_-]+$")


def _tarkista_nimi(nimi):
    if not NIMI_RE.match(nimi or ""):
        raise ValueError(f"Virheellinen nimi {nimi!r}: salli vain a-z, 0-9, _ ja -.")


def _aihe_polku(nimi):
    return os.path.join(AIHEET_DIR, f"{nimi}.json")


def _historia_polku(nimi):
    return os.path.join(HISTORIA_DIR, f"{nimi}.json")


# ---------- historia ----------

def lue_historia_lista(nimi):
    try:
        with open(_historia_polku(nimi), encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return []


def liita_historiaan(nimi, teksti):
    os.makedirs(HISTORIA_DIR, exist_ok=True)
    lista = lue_historia_lista(nimi)
    lista.append({"pvm": datetime.now().strftime("%Y-%m-%d %H:%M"), "teksti": teksti})
    lista = lista[-HISTORIA_MAX:]
    tmp = _historia_polku(nimi) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(lista, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _historia_polku(nimi))


def historia_tekstina(nimi):
    lista = lue_historia_lista(nimi)
    if not lista:
        return ""
    return "\n\n".join(f"[{e['pvm']}]\n{e['teksti']}" for e in lista)


# ---------- pi headless ----------

def poimi_vastaus(stdout):
    # Lopullinen vastaus = viimeisen assistant-roolisen message_end-tapahtuman tekstit.
    # Sama logiikka kuin scripts/telegram/telegram_bridge.py:n striimausparserissa.
    teksti = None
    for rivi in stdout.splitlines():
        rivi = rivi.strip()
        if not rivi:
            continue
        try:
            tap = json.loads(rivi)
        except ValueError:
            continue
        if tap.get("type") != "message_end":
            continue
        msg = tap.get("message") or {}
        if msg.get("role") != "assistant" or msg.get("stopReason") in ("error", "aborted"):
            continue
        osat = [c.get("text", "") for c in (msg.get("content") or [])
                if c.get("type") == "text"]
        koottu = "".join(osat).strip()
        if koottu:
            teksti = koottu
    return teksti


def aja_pi_headless(prompt, session_id):
    komento = ["pi", "--mode", "json", "--session-id", session_id]
    malli = os.environ.get("PI_MALLI", "").strip()
    if malli:
        komento += ["--model", malli]
    komento += [prompt]
    try:
        tulos = subprocess.run(komento, capture_output=True, text=True,
                               timeout=PI_AIKAKATKAISU)
    except subprocess.TimeoutExpired:
        return None, "pi-ajo aikakatkaistiin"
    except FileNotFoundError:
        return None, "pi-komentoa ei löydy"
    vastaus = poimi_vastaus(tulos.stdout or "")
    if not vastaus and tulos.returncode != 0:
        return None, f"pi rc={tulos.returncode}: {(tulos.stderr or '').strip()[:300]}"
    return vastaus, None


def rakenna_prompt(aihe, historia):
    osat = [
        f"Tehtäväsi on seurata seuraavaa aihetta ja tuottaa tiivis päivitys suomeksi:\n{aihe}",
        "Käytä staan-web-search -skilliä ajantasaisen tiedon hakuun. Rajaa haku tarvittaessa "
        "luotettaviin lähteisiin (esim. verkkokaupat --include-domains). Mainitse lähde-URLit. "
        "Jos jokin tieto (esim. hinta) on epävarma tai ei löydy, sano se suoraan äläkä arvaa.",
    ]
    if historia:
        osat.append("Aiemmat päivitykset (vanhin ensin). Kerro erityisesti MIKÄ ON MUUTTUNUT "
                    f"edellisestä:\n{historia}")
    osat.append("Pidä vastaus lyhyenä ja Telegramiin sopivana (n. 5–10 riviä).")
    return "\n\n".join(osat)


# ---------- Telegram ----------

def laheta_telegram(viesti, chat=None):
    laheta = os.path.join(TELEGRAM_DIR, "laheta.py")
    cmd = [sys.executable, laheta, "--raaka", viesti]
    if chat:
        cmd += ["--chat", str(chat)]
    subprocess.run(cmd, check=False)


# ---------- määrittelyt ----------

def lue_aihe(nimi):
    polku = _aihe_polku(nimi)
    if not os.path.exists(polku):
        raise SystemExit(f"Tuntematon aihe: {nimi}")
    with open(polku, encoding="utf-8") as f:
        return json.load(f)


# ---------- komennot ----------

def komento_luo(nimi, aikataulu, aihe, chat=None):
    _tarkista_nimi(nimi)
    os.makedirs(AIHEET_DIR, exist_ok=True)
    maaritys = {
        "nimi": nimi, "aihe": aihe, "aikataulu": aikataulu, "chat": chat,
        "luotu": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    with open(_aihe_polku(nimi), "w", encoding="utf-8") as f:
        json.dump(maaritys, f, ensure_ascii=False, indent=2)
    komento = AJA_KOMENTO_MALLI.format(nimi=nimi)
    return cron_hallinta.luo_ajastus(nimi, aikataulu, komento,
                                     loki=os.path.join(LOKI_DIR, f"{nimi}.log"))


def komento_listaa():
    if not os.path.isdir(AIHEET_DIR):
        return []
    tulos = []
    for f in sorted(os.listdir(AIHEET_DIR)):
        if not f.endswith(".json"):
            continue
        try:
            with open(os.path.join(AIHEET_DIR, f), encoding="utf-8") as fh:
                tulos.append(json.load(fh))
        except (ValueError, OSError):
            continue
    return tulos


def komento_poista(nimi):
    _tarkista_nimi(nimi)
    poistettu = False
    for polku in (_aihe_polku(nimi), _historia_polku(nimi)):
        if os.path.exists(polku):
            os.remove(polku)
            poistettu = True
    if cron_hallinta.poista_ajastus(nimi):
        poistettu = True
    return poistettu


def komento_aja(nimi):
    # Cronin sisääntulopiste. Palauttaa tokenit/avaimet cron-kontekstissa.
    peri_kontin_ymparisto()
    maaritys = lue_aihe(nimi)
    prompt = rakenna_prompt(maaritys.get("aihe", ""), historia_tekstina(nimi))
    pvm = datetime.now().strftime("%Y%m%d")
    vastaus, virhe = aja_pi_headless(prompt, f"seuraaja-{nimi}-{pvm}")
    os.makedirs(LOKI_DIR, exist_ok=True)
    if not vastaus:
        print(f"[{nimi}] ei vastausta: {virhe}", flush=True)
        return
    liita_historiaan(nimi, vastaus)
    laheta_telegram(vastaus, maaritys.get("chat"))
    print(f"[{nimi}] valmis, lähetetty Telegramiin.", flush=True)


def main():
    p = argparse.ArgumentParser(description="Aiheen seuranta ajassa (pi + Telegram).")
    ali = p.add_subparsers(dest="alikomento", required=True)

    pl = ali.add_parser("luo", help="Luo aihe-seuranta + ajastus.")
    pl.add_argument("--nimi", required=True)
    pl.add_argument("--aikataulu", required=True, help='5-kenttäinen cron, esim. "0 9 * * *"')
    pl.add_argument("--aihe", required=True, help="Mitä seurataan ja mitä halutaan tietää.")
    pl.add_argument("--chat", help="Kohde-chat-id (oletus TELEGRAM_SALLITUT_CHATIT).")

    ali.add_parser("listaa", help="Listaa seurattavat aiheet.")

    pp = ali.add_parser("poista", help="Poista aihe-seuranta + ajastus.")
    pp.add_argument("--nimi", required=True)

    pa = ali.add_parser("aja", help="Aja seuranta kerran (cronin käyttämä).")
    pa.add_argument("nimi")

    a = p.parse_args()
    try:
        if a.alikomento == "luo":
            polku = komento_luo(a.nimi, a.aikataulu, a.aihe, a.chat)
            print(f"Aihe-seuranta luotu: {a.nimi} (aikataulu {a.aikataulu}). Cron: {polku}")
        elif a.alikomento == "listaa":
            rivit = komento_listaa()
            if not rivit:
                print("(ei seurattavia aiheita)")
            for m in rivit:
                print(f"- {m.get('nimi')}: [{m.get('aikataulu')}] {(m.get('aihe') or '')[:60]}")
        elif a.alikomento == "poista":
            print("Poistettu." if komento_poista(a.nimi) else "Ei löytynyt.")
        elif a.alikomento == "aja":
            komento_aja(a.nimi)
    except ValueError as e:
        sys.exit(f"Virhe: {e}")


if __name__ == "__main__":
    main()
