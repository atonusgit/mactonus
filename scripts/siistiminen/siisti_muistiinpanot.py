import subprocess, os, sys, json
from datetime import datetime, date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import MALLI_TEKSTIT
from llm_apu import kysy_llm

VAULT = "/vault"
MAKSIMI = 4

def log(viesti):
    aika = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{aika}: {viesti}", flush=True)

def etsi_tiedostot():
    result = subprocess.run(
        'find /vault -name "*.md" -type f -printf "%T@ %p\n" | sort -rn | cut -d\' \' -f2-',
        shell=True, capture_output=True, text=True
    )
    return [r for r in result.stdout.strip().split("\n") if r and "/vault/mactonus" not in r]

def on_siistittava(sisalto):
    return "*[siisti]*" in sisalto

def on_kuvatiedosto(polku):
    nimi = os.path.basename(polku).lower()
    return ".png" in nimi or ".jpg" in nimi or ".jpeg" in nimi

def poista_siisti_merkinta(sisalto):
    return sisalto.replace("*[siisti]*", "").strip()

def siisti_tiedosto(polku, sisalto):
    kehote = f"""Siisti seuraava muistiinpano. Kirjoita se puhtaaksi ja jäsenneltyyn muotoon suomeksi.
Säilytä kaikki olennainen tieto. Älä lisää uutta tietoa. Älä muuta rakennetta radikaalisti.
Pidä ![[Kuvatiedosto.png]] -kohdat muuttumattomina, koska ne ovat kuvareferenssejä.
Lisää tiedoston loppuun merkintä: *[Päivitetty: {date.today()}]*

Muistiinpano:
{sisalto}

Palauta vain siistitty muistiinpano, ei selityksiä."""
    return kysy_llm(kehote, malli=MALLI_TEKSTIT)

def main():
    log("Aloitetaan muistiinpanojen siistiminen")
    tiedostot = etsi_tiedostot()
    log(f"Löydettiin {len(tiedostot)} tiedostoa")
    laskuri = 0

    for polku in tiedostot:
        if laskuri >= MAKSIMI:
            log(f"Maksimi ({MAKSIMI}) saavutettu.")
            break

        if not os.path.isfile(polku):
            continue

        try:
            with open(polku, "r", encoding="utf-8") as f:
                sisalto = f.read()
        except Exception as e:
            log(f"Virhe luettaessa {polku}: {e}")
            continue

        if on_kuvatiedosto(polku):
            log(f"Ohitetaan (kuvatiedosto): {polku}")
            continue

        if not on_siistittava(sisalto):
            continue

        log(f"Siistitään: {polku}")
        sisalto_ilman_merkintaa = poista_siisti_merkinta(sisalto)
        uusi_sisalto = siisti_tiedosto(polku, sisalto_ilman_merkintaa)

        if uusi_sisalto:
            with open(polku, "w", encoding="utf-8") as f:
                f.write(uusi_sisalto)
            log(f"Valmis: {polku}")
            laskuri += 1
        else:
            log(f"Virhe siistimisessä: {polku}")

    log(f"Siisittiin {laskuri} tiedostoa.")

if __name__ == "__main__":
    main()