import json, os, sys, urllib.request, urllib.error

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import MALLI_TEKSTIT, OLLAMA_URL, OLLAMA_AIKAKATKAISU

tiedosto = sys.argv[1]
sessio = sys.argv[2]
kansio = sys.argv[3]

with open(tiedosto, "r") as f:
    teksti = f.read(500)

# Skripti ajetaan hostilla; config:n URL on kontin POV (host.docker.internal).
host_url = OLLAMA_URL.replace("host.docker.internal", "localhost")

payload = json.dumps({
    "model": MALLI_TEKSTIT,
    "prompt": f"Anna lyhyt 2-4 sanan kuvaava nimi tälle nauhoitukselle. Käytä väliviivoja. Ei erikoismerkkejä. Vain nimi, ei selityksiä.\n\n{teksti}",
    "stream": False
}).encode("utf-8")

req = urllib.request.Request(
    host_url,
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST",
)

try:
    with urllib.request.urlopen(req, timeout=OLLAMA_AIKAKATKAISU) as resp:
        data = json.loads(resp.read().decode("utf-8"))
except (urllib.error.URLError, TimeoutError, OSError) as e:
    print(f"⚠ Nimeäminen ohitettu (Ollama ei vastannut): {e}", file=sys.stderr)
    sys.exit(0)
except json.JSONDecodeError as e:
    print(f"⚠ Nimeäminen ohitettu (virheellinen JSON Ollamalta): {e}", file=sys.stderr)
    sys.exit(0)

vastaus = data.get("response", "").strip()
if not vastaus:
    print("⚠ Nimeäminen ohitettu (Ollama palautti tyhjän nimen)", file=sys.stderr)
    sys.exit(0)

nimi = vastaus.replace(" ", "-").lower()
nimi = "".join(c for c in nimi if c.isalnum() or c == "-")[:40].strip("-")
if not nimi:
    print("⚠ Nimeäminen ohitettu (puhdistettu nimi tyhjä)", file=sys.stderr)
    sys.exit(0)

uusi = os.path.join(kansio, f"{sessio}-{nimi}.md")
os.rename(tiedosto, uusi)
print(uusi)
