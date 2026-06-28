#!/usr/bin/env python3
# sync.py — pi:n dokumenttien KAKSISUUNTAINEN synkka Obsidian-vaultiin.
#
# Synkronoi pi-agentin ihmisluettavat dokumentit (.pi/agent/) ja vaultin
# /vault/mactonus/pi/ -kansion molempiin suuntiin. Ajetaan kontin cronista
# (conf/cron/sync_pi_vault). Vain stdlib.
#
# Periaate (konfliktiturvallinen 3-tie): tilatiedosto pitää kirjaa kunkin
# tiedoston viimeksi-synkatusta sha256:sta. Joka ajo verrataan A=.pi ja
# B=vault nykytilaa tähän:
#   - vain toinen muuttunut -> kopioi muuttunut puoli toiselle
#   - molemmat muuttuneet ja eroavat -> KONFLIKTI: .pi on kanoninen, mutta
#     vaultin versio talletetaan viereen *.konflikti-<pvm>.md ja ilmoitetaan
#   - tiedosto vain toisella puolella -> kopioi toiselle (uusi tai palautus;
#     poistoa EI propagoida, jottei vahingossa pyyhitä molemmilta)

import hashlib, json, os, shutil, subprocess, sys
from datetime import datetime

# --- polut (ylikirjoitettavissa testeissä) ---
PI_AGENT = "/root/.pi/agent"
VAULT_PI = "/vault/mactonus/pi"
PERUS = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.dirname(PERUS)
TELEGRAM_DIR = os.path.join(SCRIPTS_DIR, "telegram")
TILA_TIEDOSTO = os.path.join(PERUS, ".tila.json")

# Synkronoitavat ylätason dokumentit (suhteessa PI_AGENT / VAULT_PI -juureen).
TOP_DOKUMENTIT = ["MEMORY.md", "SOUL.md", "USER.md", "AGENTS.md", "TOOLS.md"]

ILMOITA = os.environ.get("PI_VAULT_SYNC_ILMOITA", "1").strip().lower() not in ("0", "false", "ei", "no")

sys.path.insert(0, TELEGRAM_DIR)
try:
    from telegram_api import peri_kontin_ymparisto
except Exception:  # telegram_api ei käytettävissä (esim. testi) -> ei ilmoituksia
    peri_kontin_ymparisto = None


def loki(viesti):
    aika = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{aika}: {viesti}", flush=True)


def hae_hash(polku):
    try:
        with open(polku, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except (FileNotFoundError, IsADirectoryError, NotADirectoryError):
        return None


def kopioi(lahde, kohde):
    # Atominen kopio (temp + rename).
    os.makedirs(os.path.dirname(kohde), exist_ok=True)
    tmp = f"{kohde}.tmp"
    shutil.copy2(lahde, tmp)
    os.replace(tmp, kohde)


def kerää_avaimet():
    # Suhteelliset avaimet, jotka ovat synkronoitavissa: ylädokumentit + skills/*/SKILL.md
    # kummalta tahansa puolelta löytyvät.
    avaimet = set(TOP_DOKUMENTIT)
    for juuri in (PI_AGENT, VAULT_PI):
        skills = os.path.join(juuri, "skills")
        if os.path.isdir(skills):
            for nimi in os.listdir(skills):
                if os.path.isfile(os.path.join(skills, nimi, "SKILL.md")):
                    avaimet.add(f"skills/{nimi}/SKILL.md")
    return avaimet


def lue_tila():
    try:
        with open(TILA_TIEDOSTO, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {}


def tallenna_tila(tila):
    os.makedirs(os.path.dirname(TILA_TIEDOSTO), exist_ok=True)
    tmp = f"{TILA_TIEDOSTO}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(tila, f, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(tmp, TILA_TIEDOSTO)


def konfliktipolku(b_polku):
    base, ext = os.path.splitext(b_polku)
    leima = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{base}.konflikti-{leima}{ext}"


def kasittele_avain(key, tila, viestit):
    # Palauttaa uuden tilahashin avaimelle, tai None jos avain poistetaan tilasta.
    A = os.path.join(PI_AGENT, key)
    B = os.path.join(VAULT_PI, key)
    hA, hB = hae_hash(A), hae_hash(B)
    S = tila.get(key)

    if hA is None and hB is None:
        return None                      # ei kummallakaan -> pois tilasta
    if hA == hB:
        return hA                        # jo synkassa

    # Vain toinen puoli olemassa -> kopioi toiselle (uusi tai palautus).
    if hB is None:
        kopioi(A, B)
        if S is None:
            loki(f"uusi .pi -> vault: {key}")
        else:
            loki(f"palautettu .pi -> vault: {key} (poisto ei propagoi)")
            viestit.append(f"Vaultista poistettu {key} palautettiin (.pi:n versio säilyy).")
        return hA
    if hA is None:
        kopioi(B, A)
        if S is None:
            loki(f"uusi vault -> .pi: {key}")
        else:
            loki(f"palautettu vault -> .pi: {key} (poisto ei propagoi)")
            viestit.append(f".pi:stä poistettu {key} palautettiin (vaultin versio säilyy).")
        return hB

    # Molemmat olemassa mutta eroavat.
    if hB == S:                          # vain A muuttunut
        kopioi(A, B)
        loki(f"päivitetty .pi -> vault: {key}")
        return hA
    if hA == S:                          # vain B muuttunut
        kopioi(B, A)
        loki(f"päivitetty vault -> .pi: {key}")
        return hB

    # Molemmat muuttuneet ja eroavat -> konflikti. .pi kanoninen, vaultin versio talteen.
    kpolku = konfliktipolku(B)
    shutil.copy2(B, kpolku)
    kopioi(A, B)
    loki(f"KONFLIKTI {key}: vaultin versio -> {os.path.basename(kpolku)}, .pi voitti")
    viestit.append(f"Konflikti: {key}. Vaultin versio talletettiin nimellä "
                   f"{os.path.basename(kpolku)}; .pi:n versio jäi voimaan.")
    return hA


def ilmoita_telegram(viestit):
    if not viestit or not ILMOITA:
        return
    if peri_kontin_ymparisto:
        try:
            peri_kontin_ymparisto()
        except Exception:
            pass
    teksti = "🔁 pi↔vault-synkka:\n" + "\n".join(f"- {v}" for v in viestit)
    laheta = os.path.join(TELEGRAM_DIR, "laheta.py")
    subprocess.run([sys.executable, laheta, teksti], check=False)


def synkkaa():
    tila = lue_tila()
    viestit = []
    uusi_tila = {}
    for key in sorted(kerää_avaimet()):
        tulos = kasittele_avain(key, tila, viestit)
        if tulos is not None:
            uusi_tila[key] = tulos
    tallenna_tila(uusi_tila)
    ilmoita_telegram(viestit)
    return viestit


if __name__ == "__main__":
    synkkaa()
