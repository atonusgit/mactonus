import subprocess, os, sys, json, atexit, signal
from datetime import datetime, date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import MALLI_TEKSTIT
from llm_apu import kysy_llm

LOCK_FILE = "/tmp/luo_yhteenveto.lock"

def log(viesti):
    aika = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{aika}: {viesti}", flush=True)


def poista_lock():
    """Poista lock-tiedosto jos se on olemassa."""
    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
    except Exception:
        pass


def aseta_lock():
    """Yritä luoda lock-tiedosto. Palauttaa True jos onnistuu, False jos lock on jo olemassa."""
    try:
        # Avataan tiedosto eksklusiivisella lukulla (O_CREAT | O_EXCL)
        fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
        return True
    except FileExistsError:
        return False

def on_sallittu_tiedosto(polku):
    """Suodattaa pois .DS_Store ja binääritiedostot."""
    nimi = os.path.basename(polku)
    if nimi == ".DS_Store":
        return False
    # Binääritiedostot: .png, .jpg, .jpeg, .gif, .pdf, .bin, .exe, .dll, .so, .pyc, .wav, .mp3, .mp4, .zip, .tar, .gz
    binääripäätteet = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".bin", ".exe", ".dll", ".so", ".pyc", ".wav", ".mp3", ".mp4", ".zip", ".tar", ".gz", ".tgz", ".rar", ".7z"}
    if os.path.splitext(nimi)[1].lower() in binääripäätteet:
        return False
    return True

def etsi_muokatut_tiedostot(juuripolku, alkupaiva, loppupaiva):
    """Etsii tiedostot jotka on muokattu annettuina päivämääriä välillä."""
    result = subprocess.run(
        f'find "{juuripolku}" -type f -newermt "{alkupaiva}" ! -newermt "{loppupaiva}" -printf "%p\n"',
        shell=True, capture_output=True, text=True
    )
    
    tiedostot = [r for r in result.stdout.strip().split("\n") if r]
    # Suodata pois skriptikansiot ja ei-sallitut tiedostot
    tiedostot = [t for t in tiedostot if "/mactonus" not in t and on_sallittu_tiedosto(t)]
    return tiedostot

def lue_tiedoston_sisalto(polku, maksimi_pituus=8000):
    """Lukee tiedoston sisällön ja palauttaa sen katkaistuna jos liian pitkä."""
    try:
        with open(polku, "r", encoding="utf-8") as f:
            sisalto = f.read()
        # Katkaise liian pitkät tiedostot
        if len(sisalto) > maksimi_pituus:
            sisalto = sisalto[:maksimi_pituus] + "\n\n... (katkaistu)"
        return sisalto
    except Exception as e:
        log(f"Virhe luettaessa {polku}: {e}")
        return None

def luo_yhteenveto(tiedostot_ja_sisallot, on_maanantai=False):
    """Luo yhteenvedon tiedostoista käyttäen MALLI_TEKSTIT mallia."""
    if not tiedostot_ja_sisallot:
        return None
    
    tiedostot_tekstina = ""
    for polku, sisalto in tiedostot_ja_sisallot:
        tiedostot_tekstina += f"\n\n--- {polku} ---\n\n{sisalto}\n"
    
    ajanjakso = "edellisen viikon" if on_maanantai else "eilisen päivän"
    
    prompt = f"""Luon seuraavista tiedostoista ERITTÄIN TIIVIN yhteenvedon suomeksi.
Tiedostot on muokattu {ajanjakso}.

Sisältö:
{tiedostot_tekstina}

OHJEET YHTEENVEDOLLE:
1. Kirjoita tarkalleen viisi lausetta yleisestä sisällöstä ja keskeisistä teemoista.
2. Lisää tarkalleen viisi bullet pointia (- merkillä) tärkeimmistä yksityiskohdista.
3. Päätä yhteenveto tarkalleen kahdella lauseella, jotka kiteyttävät tärkeimmän noston päivälle.
4. Lisää loppuun "Lähteet:" otsikon alla luettelona kaikki lähdetiedostot Obsidian-linkkeinä (muodossa [[tiedostonnimi.md]] ilman polkuja, - merkillä).

Palauta vain yhteenveto markdown-muodossa. Älä sisällytä mitään muuta tekstiä.
Formatoi:
- Yleiskuvaus (5 lausetta, tavallinen teksti)
- Bullet pointit (tarkalleen 5 kpl, - merkillä)
- Tärkein nosto (2 lausetta, tavallinen teksti)
- Lähteet: (luettelo lähdetiedostoista)

Älä käytä otsikoita, älä selitä, älä lisää teknisiä merkintöjä."""
    
    try:
        return kysy_llm(prompt, malli=MALLI_TEKSTIT)
    except Exception as e:
        log(f"Virhe yhteenvetoa luotaessa: {e}")
        return None

def main():
    # Tarkista ja aseta lock
    if not aseta_lock():
        log("Skripti on jo ajossa. Keskeytetään.")
        sys.exit(0)
    
    # Varmista lockin poisto myös keskeytyksen sattuessa
    atexit.register(poista_lock)
    
    # Käytä signaaleja lockin poistoon
    def handler(signum, frame):
        poista_lock()
        sys.exit(1)
    
    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)
    
    VAULT = "/vault"
    
    if not os.path.isdir(VAULT):
        log(f"Polkua {VAULT} ei löydy tai se ei ole kansio.")
        sys.exit(1)
    
    paivamaara = date.today().strftime("%d.%m")
    yhteenveto_tiedosto = f"yhteenveto_{paivamaara}.md"
    yhteenveto_polku = os.path.join(VAULT, yhteenveto_tiedosto)
    
    # Tarkista onko yhteenveto-tiedosto jo olemassa
    if os.path.exists(yhteenveto_polku):
        log(f"Tiedosto {yhteenveto_polku} on jo olemassa. Skriptin suoritus keskeytetään.")
        sys.exit(0)
    
    # Tarkista onko tänään maanantai (0 = maanantai)
    on_maanantai = date.today().weekday() == 0
    
    if on_maanantai:
        # Edellisen viikon lauantai ja sunnuntai
        eilinen = date.today() - timedelta(days=1)
        viikon_alku = eilinen - timedelta(days=6)  # Edellisen viikon maanantai
        viikon_loppu = eilinen  # Sunnuntai
        
        log(f"Maanantai: haetaan edellisen viikon ({(viikon_alku).strftime("%Y-%m-%d")} - {viikon_loppu.strftime("%Y-%m-%d")}) muokatut tiedostot")
        tiedostot = etsi_muokatut_tiedostot(VAULT, viikon_alku.strftime("%Y-%m-%d"), viikon_loppu.strftime("%Y-%m-%d"))
    else:
        # Normaalitarkistus: eilisen päivän tiedostot
        eilen = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
        log("Etsitään eilen muokattuja tiedostoja...")
        tiedostot = etsi_muokatut_tiedostot(VAULT, eilen, date.today().strftime("%Y-%m-%d"))
    
    log(f"Löydettiin {len(tiedostot)} muokattua tiedostoa")
    
    if not tiedostot:
        log("Ei muokattuja tiedostoja löytynyt.")
        sys.exit(0)
    
    # Lue tiedostot
    tiedostot_ja_sisallot = []
    for polku in tiedostot:
        sisalto = lue_tiedoston_sisalto(polku)
        if sisalto:
            tiedostot_ja_sisallot.append((polku, sisalto))
            log(f"Luettu: {polku}")
    
    if not tiedostot_ja_sisallot:
        log("Yhtään tiedostoa ei voitu lukea.")
        sys.exit(0)
    
    log("Luodaan yhteenvetoa...")
    yhteenveto = luo_yhteenveto(tiedostot_ja_sisallot, on_maanantai)
    
    if yhteenveto:
        with open(yhteenveto_polku, "w", encoding="utf-8") as f:
            f.write(yhteenveto)
        log(f"Yhteenveto tallennettu: {yhteenveto_polku}")
    else:
        log("Yhteenvetoa ei voitu luoda.")
        sys.exit(1)

if __name__ == "__main__":
    main()
