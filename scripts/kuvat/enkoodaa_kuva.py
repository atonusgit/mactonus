import base64, json, sys, subprocess, os
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import MALLI_KUVAT, OLLAMA_URL
from tiedosto_apu import siisti_tiedostonimi

if len(sys.argv) < 2:
    print("Käyttö: python3 enkoodaa_kuva.py <kuvatiedosto> [tulostiedosto.md]")
    sys.exit(1)

kuva = sys.argv[1]
kuva_kansio = os.path.dirname(kuva)
kuva_pääte = os.path.splitext(kuva)[1]
alkup_nimi = os.path.basename(kuva)
nykyinen_nimi = alkup_nimi

# Tulostiedosto argumentista tai oletuksena kuva_teksti.md
if len(sys.argv) >= 3:
    uusi_md = sys.argv[2]
else:
    pohja = os.path.splitext(alkup_nimi)[0]
    uusi_md = os.path.join(kuva_kansio, f"{pohja}_teksti.md")

KEHOTE_TIEDOSTO = "/vault/mactonus/Kehotteet/Analysoi kuva.md"
if os.path.isfile(KEHOTE_TIEDOSTO):
    with open(KEHOTE_TIEDOSTO, "r", encoding="utf-8") as f:
        kehote = f.read()
else:
    kehote = """Analysoi tämä kuva suomeksi. Vastaa JSON-muodossa:
{
  "nimi": "lyhyt-kuvaava-nimi-ilman-erikoismerkkeja",
  "kuvaus": "Yksityiskohtainen kuvaus kuvasta suomeksi."
}
Nimi: max 5 sanaa, väliviiva erottimena, ei erikoismerkkejä eikä välilyöntejä."""

with open(kuva, "rb") as f:
    img = base64.b64encode(f.read()).decode()

payload = json.dumps({
    "model": MALLI_KUVAT,
    "prompt": kehote,
    "images": [img],
    "stream": False
})

with open("/tmp/request.json", "w") as f:
    f.write(payload)

print(f"Analysoidaan: {kuva}")
result = subprocess.run(
    ["curl", "-s", OLLAMA_URL,
     "-H", "Content-Type: application/json",
     "-d", "@/tmp/request.json"],
    capture_output=True, text=True
)

data = json.loads(result.stdout)
vastaus = data.get("response", "")

try:
    alku = vastaus.find("{")
    loppu = vastaus.rfind("}") + 1
    parsed = json.loads(vastaus[alku:loppu])
    nimi = parsed.get("nimi", "kuva")
    kuvaus = parsed.get("kuvaus", vastaus)
    avainsanat = parsed.get("avainsanat", [])
except Exception:
    nimi = os.path.splitext(alkup_nimi)[0]
    kuvaus = vastaus
    avainsanat = []

# Siisti nimi tiedostonimeksi (säilyttää ääkköset, korvaa kielletyt merkit).
nimi = siisti_tiedostonimi(nimi, oletus="kuva")
kuvaus = kuvaus.replace("\\n", "\n").strip()

if isinstance(avainsanat, list):
    avainsanat_teksti = ", ".join(str(x).strip() for x in avainsanat if str(x).strip())
else:
    avainsanat_teksti = str(avainsanat).strip()

# Uudelleennimeä tietyt tiedostot
UUDELLEENNIMEA_PREFIXIT = ("Screenshot", "screenshot", "IMG_", "img_", "image", "Image")

if alkup_nimi.startswith(UUDELLEENNIMEA_PREFIXIT):
    uusi_nimi = f"{nimi}{kuva_pääte}"
    uusi_kuva = os.path.join(kuva_kansio, uusi_nimi)
    uusi_md = os.path.join(kuva_kansio, f"{nimi}_teksti.md")
    nykyinen_nimi = uusi_nimi

    os.rename(kuva, uusi_kuva)
    print(f"Uudelleennimetty: {alkup_nimi} → {uusi_nimi}")

    vault = "/vault"
    for root, dirs, files in os.walk(vault):
        for tiedosto in files:
            if tiedosto.endswith(".md"):
                polku = os.path.join(root, tiedosto)
                try:
                    with open(polku, "r", encoding="utf-8") as f:
                        sisalto = f.read()
                    if alkup_nimi in sisalto:
                        uusi_sisalto = sisalto.replace(alkup_nimi, uusi_nimi)
                        with open(polku, "w", encoding="utf-8") as f:
                            f.write(uusi_sisalto)
                        print(f"Päivitetty linkki: {polku}")
                except Exception as e:
                    print(f"Virhe tiedostossa {polku}: {e}")

with open(uusi_md, "w", encoding="utf-8") as f:
    f.write(f"# {nimi.replace('-', ' ').title()}\n\n")
    f.write(f"**Alkuperäinen:** {alkup_nimi}\n")
    f.write(f"Kuva: [[{nykyinen_nimi}]]\n\n")
    f.write(f"{kuvaus}\n\n")
    if avainsanat_teksti:
        f.write(f"**Avainsanat:**\n{avainsanat_teksti}\n\n")
    f.write(f"*[Luotu automaattisesti: {date.today()}]*\n")
    f.write("\n#siisti-kuvailutulkkaus\n")

print(f"Tallennettu: {uusi_md}")

uusi_pohja = os.path.splitext(os.path.basename(uusi_md))[0]
print(f"UUSI_POHJA:{uusi_pohja}")