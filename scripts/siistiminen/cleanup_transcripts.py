import subprocess, os, sys, json
from datetime import datetime, date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import MALLI_TEKSTIT, OLLAMA_URL

KANSIO = "/vault/mactonus/Nauhoitukset"
MAKSIMI = 4
PROMPTS_KANSIO = "/vault/mactonus/Dokumenttimuoto-kehotteet"

def log(viesti):
    aika = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{aika}: {viesti}", flush=True)

def lataa_prompt(nimi):
    polku = os.path.join(PROMPTS_KANSIO, f"{nimi}.md")
    if not os.path.isfile(polku):
        print(f"Virhe: prompt-tiedostoa '{polku}' ei löydy.")
        sys.exit(1)
    with open(polku, "r", encoding="utf-8") as f:
        return f.read()

def valitse_prompt():
    if not os.path.isdir(PROMPTS_KANSIO):
        print(f"Virhe: prompts-kansiota '{PROMPTS_KANSIO}' ei löydy.")
        sys.exit(1)

    vaihtoehdot = [f.replace(".md", "") for f in os.listdir(PROMPTS_KANSIO) if f.endswith(".md")]

    if not vaihtoehdot:
        print("Virhe: ei prompt-tiedostoja kansiossa.")
        sys.exit(1)

    print("\nSaatavilla olevat promptit:")
    for i, v in enumerate(sorted(vaihtoehdot), 1):
        print(f"  {i}. {v}")

    valinta = input("\nValitse prompt (nimi tai numero): ").strip()

    if valinta.isdigit():
        idx = int(valinta) - 1
        if 0 <= idx < len(vaihtoehdot):
            return sorted(vaihtoehdot)[idx]
        else:
            print("Virhe: virheellinen numero.")
            sys.exit(1)

    if valinta in vaihtoehdot:
        return valinta

    print(f"Virhe: '{valinta}' ei löydy.")
    sys.exit(1)

def on_siistitty(polku):
    # Tarkista tiedostonimi
    kansio = os.path.dirname(polku)
    pohja = os.path.basename(polku).replace(".md", "")
    for tiedosto in os.listdir(kansio):
        if tiedosto.startswith(pohja + "_") and tiedosto.endswith(".md"):
            return True
    
    # Tarkista sisältö
    try:
        with open(polku, "r", encoding="utf-8") as f:
            sisalto = f.read()
        if "*[Siistitty:" in sisalto:
            return True
    except:
        pass
    
    return False

def siisti_tiedosto(polku, sisalto, prompt_pohja):
    prompt = prompt_pohja.replace("{sisalto}", sisalto).replace("{date}", str(date.today()))

    payload = json.dumps({
        "model": MALLI_TEKSTIT,
        "prompt": prompt,
        "stream": False
    })

    with open("/tmp/siisti_nauhoitus.json", "w") as f:
        f.write(payload)

    result = subprocess.run(
        ["curl", "-s", OLLAMA_URL,
         "-H", "Content-Type: application/json",
         "-d", "@/tmp/siisti_nauhoitus.json"],
        capture_output=True, text=True
    )

    data = json.loads(result.stdout)
    return data.get("response", "")

def main():
    # Valitse prompt
    if len(sys.argv) > 1:
        prompt_nimi = sys.argv[1]
        prompt_pohja = lataa_prompt(prompt_nimi)
    else:
        prompt_nimi = valitse_prompt()
        prompt_pohja = lataa_prompt(prompt_nimi)

    log(f"Käytetään promptia: {prompt_nimi}")
    log("Aloitetaan nauhoitusten siistiminen")
    laskuri = 0

    for tiedosto in sorted(os.listdir(KANSIO)):
        if laskuri >= MAKSIMI:
            log(f"Maksimi ({MAKSIMI}) saavutettu.")
            break

        if not tiedosto.endswith(".md"):
            continue
        if "_siistitty" in tiedosto or f"_{prompt_nimi}" in tiedosto:
            continue

        polku = os.path.join(KANSIO, tiedosto)

        if on_siistitty(polku):
            log(f"Ohitetaan (jo siistitty): {tiedosto}")
            continue

        try:
            with open(polku, "r", encoding="utf-8") as f:
                sisalto = f.read()
        except Exception as e:
            log(f"Virhe luettaessa {polku}: {e}")
            continue

        log(f"Siistitään: {tiedosto}")
        uusi_sisalto = siisti_tiedosto(polku, sisalto, prompt_pohja)

        if uusi_sisalto:
            siistitty = polku.replace(".md", f"_{prompt_nimi}.md")
            with open(siistitty, "w", encoding="utf-8") as f:
                f.write(uusi_sisalto)
            log(f"Valmis: {os.path.basename(siistitty)}")
            laskuri += 1
        else:
            log(f"Virhe siistimisessä: {tiedosto}")

    log(f"Siisittiin {laskuri} tiedostoa.")

if __name__ == "__main__":
    main()