"""Jalosta kuvailutulkkausten _teksti.md-tiedostot isommalla mallilla.

Käy läpi /vault/**/Liitteet/*_teksti.md -tiedostot, joissa on
#siisti-kuvailutulkkaus-tägi, ja siistii kuvauksen + avainsanat
MALLI_TEKSTIT-mallilla (oikeinkirjoitus ja avainsanojen selkeytys).
Poistaa tägin onnistuneen jalostuksen jälkeen.
"""
import subprocess, os, sys, json, re, fcntl
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import MALLI_TEKSTIT
from llm_apu import kysy_llm

VAULT = "/vault"
MAKSIMI = 4
KEHOTE_TIEDOSTO = "/vault/mactonus/Kehotteet/Siisti kuvailutulkkaus.md"
TAGI = "#siisti-kuvailutulkkaus"
LUKKO = "/tmp/jalosta_kuvatekstit.lock"

def log(viesti):
    aika = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{aika}: {viesti}", flush=True)

def etsi_tiedostot():
    result = subprocess.run(
        ["find", VAULT, "-path", "*/Liitteet/*_teksti.md", "-type", "f"],
        capture_output=True, text=True
    )
    polut = [p for p in result.stdout.strip().split("\n") if p]
    jalostettavat = []
    for polku in polut:
        try:
            with open(polku, "r", encoding="utf-8") as f:
                sisalto = f.read()
            # Hae tägi erillisenä sanana, ei osana pidempää tägiä
            if re.search(rf"(?:^|\s){re.escape(TAGI)}(?:\s|$)", sisalto, re.MULTILINE):
                jalostettavat.append(polku)
        except Exception:
            continue
    return jalostettavat

def lataa_kehote_pohja():
    if os.path.isfile(KEHOTE_TIEDOSTO):
        with open(KEHOTE_TIEDOSTO, "r", encoding="utf-8") as f:
            return f.read()
    return """Siisti seuraava kuva-analyysi suomeksi. Korjaa kirjoitusvirheet ja selkeytä avainsanat. Älä lisää uutta tietoa äläkä muuta kuvauksen sisältöä — vain kieliasu ja oikeinkirjoitus.

Vastaa vain JSON-muodossa, ilman selityksiä tai pohdintaa:
{
  "kuvaus": "Siistitty kuvaus suomeksi.",
  "avainsanat": ["avainsana1", "avainsana2"]
}

Alkuperäinen kuvaus:
{kuvaus}

Alkuperäiset avainsanat:
{avainsanat}"""

def parsi(sisalto):
    otsikko, alkup_rivi, kuva_rivi, luotu_rivi, avainsanat = "", "", "", "", ""
    kuvaus_rivit = []
    tila = "alku"
    for rivi in sisalto.split("\n"):
        if rivi.startswith("# "):
            otsikko = rivi
        elif rivi.startswith("**Alkuperäinen:**"):
            alkup_rivi = rivi
            tila = "kuvaus"
        elif rivi.startswith("Kuva: [["):
            kuva_rivi = rivi
        elif rivi.startswith("**Avainsanat:**"):
            tila = "avainsanat"
        elif rivi.startswith("*[Luotu automaattisesti:"):
            luotu_rivi = rivi
            tila = "loppu"
        elif rivi.strip() == TAGI:
            tila = "loppu"
        elif tila == "kuvaus":
            kuvaus_rivit.append(rivi)
        elif tila == "avainsanat" and rivi.strip():
            avainsanat = rivi.strip()
            tila = "loppu"
    return otsikko, alkup_rivi, kuva_rivi, luotu_rivi, "\n".join(kuvaus_rivit).strip(), avainsanat

def jalosta(kuvaus, avainsanat, kehote_pohja):
    kehote = kehote_pohja.replace("{kuvaus}", kuvaus).replace(
        "{avainsanat}", avainsanat if avainsanat else "(ei avainsanoja)")
    vastaus = kysy_llm(kehote, malli=MALLI_TEKSTIT)
    alku = vastaus.find("{")
    loppu = vastaus.rfind("}") + 1
    parsed = json.loads(vastaus[alku:loppu])
    uusi_kuvaus = parsed.get("kuvaus", kuvaus).replace("\\n", "\n").strip()
    uudet = parsed.get("avainsanat", avainsanat)
    if isinstance(uudet, list):
        uudet_teksti = ", ".join(str(x).strip() for x in uudet if str(x).strip())
    else:
        uudet_teksti = str(uudet).strip()
    return uusi_kuvaus, uudet_teksti

def kirjoita(polku, otsikko, alkup_rivi, kuva_rivi, luotu_rivi, kuvaus, avainsanat):
    with open(polku, "w", encoding="utf-8") as f:
        if otsikko:
            f.write(f"{otsikko}\n\n")
        if alkup_rivi:
            f.write(f"{alkup_rivi}\n")
            if kuva_rivi:
                f.write(f"{kuva_rivi}\n\n")
            else:
                f.write("\n")
        elif kuva_rivi:
            f.write(f"{kuva_rivi}\n\n")
        f.write(f"{kuvaus}\n\n")
        if avainsanat:
            f.write(f"**Avainsanat:**\n{avainsanat}\n\n")
        if luotu_rivi:
            f.write(f"{luotu_rivi}\n")

def main():
    lukko_fd = open(LUKKO, "w")
    try:
        fcntl.flock(lukko_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log("Edellinen ajo vielä kesken, ohitetaan.")
        lukko_fd.close()
        return

    kehote_pohja = lataa_kehote_pohja()
    tiedostot = etsi_tiedostot()
    log(f"Löydettiin {len(tiedostot)} jalostettavaa tiedostoa")
    laskuri = 0
    for polku in tiedostot:
        if laskuri >= MAKSIMI:
            log(f"Maksimi ({MAKSIMI}) saavutettu.")
            break
        try:
            with open(polku, "r", encoding="utf-8") as f:
                sisalto = f.read()
        except Exception as e:
            log(f"Virhe luettaessa {polku}: {e}")
            continue

        otsikko, alkup_rivi, kuva_rivi, luotu_rivi, kuvaus, avainsanat = parsi(sisalto)
        if not kuvaus:
            log(f"Ohitetaan (ei kuvausta): {polku}")
            continue

        log(f"Jalostetaan: {polku}")
        try:
            uusi_kuvaus, uudet_avainsanat = jalosta(kuvaus, avainsanat, kehote_pohja)
        except Exception as e:
            log(f"Virhe jalostuksessa {polku}: {e}")
            continue

        kirjoita(polku, otsikko, alkup_rivi, kuva_rivi, luotu_rivi, uusi_kuvaus, uudet_avainsanat)
        log(f"Valmis: {polku}")
        laskuri += 1

    log(f"Jalostettiin {laskuri} tiedostoa.")

if __name__ == "__main__":
    main()
