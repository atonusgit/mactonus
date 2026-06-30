import json, os, sys, urllib.request, urllib.error

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import MALLI_TEKSTIT, LLM_URL, LLM_AIKAKATKAISU
from llm_apu import kysy_llm

tiedosto = sys.argv[1]
sessio = sys.argv[2]
kansio = sys.argv[3]

with open(tiedosto, "r") as f:
    teksti = f.read(500)

# Skripti ajetaan hostilla; config:n URL on kontin POV (host.docker.internal).
host_url = LLM_URL.replace("host.docker.internal", "localhost")

kehote = (f"Anna lyhyt 2-4 sanan kuvaava nimi tälle nauhoitukselle. "
          f"Käytä väliviivoja. Ei erikoismerkkejä. Vain nimi, ei selityksiä.\n\n{teksti}")

try:
    vastaus = kysy_llm(kehote, malli=MALLI_TEKSTIT, url=host_url,
                       aikakatkaisu=LLM_AIKAKATKAISU).strip()
except Exception as e:
    print(f"⚠ Nimeäminen ohitettu (LLM ei vastannut): {e}", file=sys.stderr)
    sys.exit(0)

if not vastaus:
    print("⚠ Nimeäminen ohitettu (LLM palautti tyhjän nimen)", file=sys.stderr)
    sys.exit(0)

nimi = vastaus.replace(" ", "-").lower()
nimi = "".join(c for c in nimi if c.isalnum() or c == "-")[:40].strip("-")
if not nimi:
    print("⚠ Nimeäminen ohitettu (puhdistettu nimi tyhjä)", file=sys.stderr)
    sys.exit(0)

uusi = os.path.join(kansio, f"{sessio}-{nimi}.md")
os.rename(tiedosto, uusi)
print(uusi)
