#!/usr/bin/env python3
# muisti.py — pi:n keskustelumuistin hallinta: autonominen konsolidointi sessioista,
# per-päivä-tallennus, kuukausitiivistys ja rajatun MEMORY.md-näkymän kokoaminen.
#
# Alikomennot:
#   konsolidoi  Lue uudet session-rivit -> poimi pysyvät opit (Ollama) -> tämän päivän tiedosto.
#   tiivista    Yli 2 kk vanhat kuukaudet -> kuukausitiivistelmä (Ollama) + raakojen arkistointi.
#   kokoa       Regeneroi MEMORY.md = kuukausitiivistelmät + jäljellä olevat päivätiedostot.
#   migroi      Pilko nykyinen MEMORY.md:n päivälohkot päivätiedostoiksi (kertaluontoinen).
#   aja         konsolidoi -> tiivista -> kokoa (cronin sisääntulopiste).
#
# Vain stdlib + config.py (Ollama). LLM-työ suoralla Ollama-kutsulla kuten daily.py.

import glob, json, os, re, shutil, sys, urllib.request
from datetime import datetime

PI_AGENT = "/root/.pi/agent"
SESSIOT_DIR = os.path.join(PI_AGENT, "sessions")
MEMORY_DIR = os.path.join(PI_AGENT, "memory")
PAIVAT_DIR = os.path.join(MEMORY_DIR, "paivat")
TIIVISTELMAT_DIR = os.path.join(MEMORY_DIR, "tiivistelmat")
ARKISTO_DIR = os.path.join(MEMORY_DIR, "arkisto")
MEMORY_MD = os.path.join(PI_AGENT, "MEMORY.md")
TILA_TIEDOSTO = os.path.join(MEMORY_DIR, ".tila.json")

# Kuinka monta merkkiä uutta keskustelua syötetään kerralla Ollamalle (raja kontekstille).
MAKS_SYOTE = 8000
TIIVISTYS_KK_RAJA = 2  # kuukausi tiivistetään kun se on väh. tämän verran kuukausia vanha

OTSIKKO = """# MEMORY.md — keskustelumuisti (GENEROITU — älä muokkaa käsin)

> Tämä tiedosto kootaan automaattisesti: kuukausitiivistelmät + viime kuukausien
> päivätiedostot (memory/paivat/). pi lukee tämän istunnon alussa.
> Uudet opit kirjataan **tämän päivän tiedostoon** memory/paivat/<pvm>.md — EI tänne.
"""

# config.py on scripts-juuressa
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import MALLI_TEKSTIT, OLLAMA_URL, OLLAMA_AIKAKATKAISU


def nyt():
    return datetime.now()


def kutsu_ollama(kehote):
    # Suora Ollama-generate-kutsu (sama malli kuin cleanup_*). Palauttaa vastaustekstin.
    data = json.dumps({"model": MALLI_TEKSTIT, "prompt": kehote, "stream": False}).encode("utf-8")
    pyynto = urllib.request.Request(OLLAMA_URL, data=data,
                                    headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(pyynto, timeout=OLLAMA_AIKAKATKAISU) as vastaus:
        return (json.load(vastaus).get("response") or "").strip()


# ---------- tila ----------

def lue_tila():
    try:
        with open(TILA_TIEDOSTO, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {}


def tallenna_tila(tila):
    _kirjoita_atomisesti(TILA_TIEDOSTO, json.dumps(tila, ensure_ascii=False, indent=2, sort_keys=True))


def _kirjoita_atomisesti(polku, sisalto):
    os.makedirs(os.path.dirname(polku), exist_ok=True)
    tmp = f"{polku}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(sisalto)
    os.replace(tmp, polku)


# ---------- päivätiedostot ----------

def paivan_polku(pvm):
    return os.path.join(PAIVAT_DIR, f"{pvm}.md")


def lisaa_lohko(pvm, otsikko, sisalto):
    # Lisää uuden lohkon päivän tiedoston loppuun (ei ylikirjoita).
    os.makedirs(PAIVAT_DIR, exist_ok=True)
    polku = paivan_polku(pvm)
    vanha = ""
    if os.path.exists(polku):
        with open(polku, encoding="utf-8") as f:
            vanha = f.read().rstrip() + "\n\n"
    lohko = f"## {otsikko}\n{sisalto.rstrip()}\n"
    _kirjoita_atomisesti(polku, vanha + lohko)


# ---------- sessioiden luku ----------

def kaikki_sessiot():
    return sorted(glob.glob(os.path.join(SESSIOT_DIR, "**", "*.jsonl"), recursive=True))


def poimi_keskustelu(rivit):
    # Poimii user/assistant-tekstit JSONL-riveistä; ohittaa thinking/toolCall-roinan.
    palat = []
    for rivi in rivit:
        rivi = rivi.strip()
        if not rivi:
            continue
        try:
            o = json.loads(rivi)
        except ValueError:
            continue
        msg = o.get("message") or {}
        rooli = msg.get("role")
        if rooli not in ("user", "assistant"):
            continue
        sis = msg.get("content")
        teksti = ""
        if isinstance(sis, str):
            teksti = sis
        elif isinstance(sis, list):
            teksti = "".join(c.get("text", "") for c in sis
                             if isinstance(c, dict) and c.get("type") == "text")
        teksti = teksti.strip()
        if teksti:
            nimi = "Käyttäjä" if rooli == "user" else "pi"
            palat.append(f"{nimi}: {teksti}")
    return "\n".join(palat)


def lue_nykymuisti():
    try:
        with open(MEMORY_MD, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""


# ---------- komennot ----------

def konsolidoi():
    tila = lue_tila()
    offsetit = tila.setdefault("sessio_offsetit", {})
    uudet_palat = []
    for polku in kaikki_sessiot():
        try:
            with open(polku, encoding="utf-8") as f:
                rivit = f.readlines()
        except OSError:
            continue
        aloitus = offsetit.get(polku, 0)
        if len(rivit) <= aloitus:
            continue
        teksti = poimi_keskustelu(rivit[aloitus:])
        if teksti:
            uudet_palat.append(teksti)
        offsetit[polku] = len(rivit)

    if uudet_palat:
        syote = "\n\n".join(uudet_palat)
        if len(syote) > MAKS_SYOTE:
            syote = syote[-MAKS_SYOTE:]  # uusin sisältö tärkein
        kehote = (
            "Olet pi-agentin muistin ylläpitäjä. Alla on uutta keskustelua. Poimi siitä VAIN "
            "pysyvät opit (käyttäjän mieltymykset, projektin tila, tehdyt päätökset ja perustelut, "
            "avoimet asiat). Älä toista mitään, mikä on jo alla olevassa nykyisessä muistissa. "
            "Vastaa lyhyinä ranskalaisina viivoina suomeksi, tai pelkkä 'EI MITÄÄN' jos ei mitään "
            "uutta pysyvää.\n\n"
            f"=== NYKYINEN MUISTI ===\n{lue_nykymuisti()}\n\n"
            f"=== UUSI KESKUSTELU ===\n{syote}\n\n=== POIMITUT UUDET OPIT ==="
        )
        try:
            vastaus = kutsu_ollama(kehote)
        except Exception as e:
            # Ollama-virhe: ÄLÄ tallenna edenneitä offsetteja, jotta sama sisältö
            # käsitellään uudelleen seuraavalla ajolla.
            print(f"konsolidoi: Ollama-virhe, yritetään uudelleen seuraavalla ajolla: {e}", flush=True)
            return
        if vastaus and "EI MITÄÄN" not in vastaus.upper():
            pvm = nyt().strftime("%Y-%m-%d")
            lisaa_lohko(pvm, f"{pvm} {nyt().strftime('%H:%M')} (auto)", vastaus)
            print(f"konsolidoi: lisätty automaattinen muistilohko {pvm}", flush=True)
        else:
            print("konsolidoi: ei uusia pysyviä oppeja", flush=True)
    tallenna_tila(tila)


def _kk_avain(pvm):
    return pvm[:7]  # "YYYY-MM-DD" -> "YYYY-MM"


def _kk_ero(a, b):
    # Kuukausien lukumäärä a:sta b:hen ("YYYY-MM").
    ay, am = map(int, a.split("-"))
    by, bm = map(int, b.split("-"))
    return (by * 12 + bm) - (ay * 12 + am)


def tiivista():
    if not os.path.isdir(PAIVAT_DIR):
        return
    tama_kk = nyt().strftime("%Y-%m")
    # ryhmittele päivätiedostot kuukausittain
    kuukaudet = {}
    for polku in glob.glob(os.path.join(PAIVAT_DIR, "*.md")):
        nimi = os.path.splitext(os.path.basename(polku))[0]  # YYYY-MM-DD
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", nimi):
            continue
        kuukaudet.setdefault(_kk_avain(nimi), []).append(polku)

    for kk, tiedostot in sorted(kuukaudet.items()):
        if _kk_ero(kk, tama_kk) < TIIVISTYS_KK_RAJA:
            continue
        kohde = os.path.join(TIIVISTELMAT_DIR, f"{kk}.md")
        if os.path.exists(kohde):
            continue  # jo tiivistetty
        osat = []
        for t in sorted(tiedostot):
            with open(t, encoding="utf-8") as f:
                osat.append(f.read())
        kehote = (
            f"Tiivistä kuukauden {kk} keskustelumuisti. Alla päivittäiset muistilohkot. "
            "Tee tiivis suomenkielinen yhteenveto pysyvistä opeista, päätöksistä ja projektin "
            "tilasta — säilytä olennainen, karsi toisto. Käytä lyhyitä ranskalaisia viivoja.\n\n"
            + "\n\n".join(osat)
        )
        try:
            tiiv = kutsu_ollama(kehote)
        except Exception as e:
            print(f"tiivista: Ollama-virhe kuukaudelle {kk}: {e}", flush=True)
            continue
        if not tiiv:
            continue
        _kirjoita_atomisesti(kohde, f"# Kuukausitiivistelmä {kk}\n\n{tiiv}\n")
        os.makedirs(ARKISTO_DIR, exist_ok=True)
        for t in tiedostot:
            shutil.move(t, os.path.join(ARKISTO_DIR, os.path.basename(t)))
        print(f"tiivista: {kk} tiivistetty ({len(tiedostot)} päivää arkistoitu)", flush=True)


def kokoa():
    osat = [OTSIKKO]
    for polku in sorted(glob.glob(os.path.join(TIIVISTELMAT_DIR, "*.md"))):
        with open(polku, encoding="utf-8") as f:
            osat.append(f.read().rstrip())
    for polku in sorted(glob.glob(os.path.join(PAIVAT_DIR, "*.md"))):
        with open(polku, encoding="utf-8") as f:
            osat.append(f.read().rstrip())
    _kirjoita_atomisesti(MEMORY_MD, "\n\n".join(osat).rstrip() + "\n")
    print(f"kokoa: MEMORY.md regeneroitu ({len(osat) - 1} lähdetiedostoa)", flush=True)


def migroi():
    # Pilkkoo nykyisen MEMORY.md:n "## YYYY-MM-DD ..." -lohkot päivätiedostoiksi.
    teksti = lue_nykymuisti()
    if not teksti:
        print("migroi: MEMORY.md tyhjä/puuttuu", flush=True)
        return
    # Etsi lohkot, jotka alkavat ## YYYY-MM-DD
    osumat = list(re.finditer(r"(?m)^## (\d{4}-\d{2}-\d{2})[^\n]*$", teksti))
    if not osumat:
        print("migroi: ei päivättyjä lohkoja", flush=True)
        return
    for i, m in enumerate(osumat):
        pvm = m.group(1)
        alku = m.start()
        loppu = osumat[i + 1].start() if i + 1 < len(osumat) else len(teksti)
        lohko = teksti[alku:loppu].rstrip()
        # poista "## " -etuliite otsikkorivistä, koska lisaa_lohko lisää sen
        otsikko_loppu = teksti.index("\n", alku) if "\n" in teksti[alku:] else loppu
        otsikko = teksti[alku + 3:otsikko_loppu].strip()
        sisalto = lohko[lohko.index("\n") + 1:].strip() if "\n" in lohko else ""
        lisaa_lohko(pvm, otsikko, sisalto)
    print(f"migroi: siirretty {len(osumat)} lohkoa päivätiedostoihin", flush=True)


def aja():
    konsolidoi()
    tiivista()
    kokoa()


def main():
    komento = sys.argv[1] if len(sys.argv) > 1 else "aja"
    {"konsolidoi": konsolidoi, "tiivista": tiivista, "kokoa": kokoa,
     "migroi": migroi, "aja": aja}.get(komento, lambda: sys.exit(
        f"Tuntematon komento: {komento} (konsolidoi|tiivista|kokoa|migroi|aja)"))()


if __name__ == "__main__":
    main()
