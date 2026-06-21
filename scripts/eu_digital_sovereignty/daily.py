#!/usr/bin/env python3
# EU Digital Sovereignty Daily - hae Staanista, tiivistä Ollamalla, lähetä Telegramiin.
import hashlib, json, os, re, subprocess, sys
from datetime import date
from html import unescape
from urllib.request import Request, urlopen
from urllib.parse import quote, urlparse
from urllib.robotparser import RobotFileParser

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TELEGRAM_DIR = os.path.join(SCRIPTS_DIR, "telegram")
sys.path.insert(0, TELEGRAM_DIR)
sys.path.insert(0, SCRIPTS_DIR)

# Cron ei peri kontin ympäristöä -> peri envit kontin pääprosessilta
# (/proc/1/environ) ENNEN kuin config ladataan, sillä config lukee MALLI_TEKSTIT:n
# env:stä jo import-hetkellä.
from telegram_api import peri_kontin_ymparisto, riisu_markdown
peri_kontin_ymparisto()
from config import MALLI_TEKSTIT, OLLAMA_URL, OLLAMA_AIKAKATKAISU  # jaetusta configista

KEY = os.environ.get("STAAN_API_KEY", "")
LIMIT = 5         # tuloksia per hakutermi, ja mallille tarjottava ehdokasmäärä
VALINTOJA = 2     # montako uutista malli valitsee ja tulkitsee viestiin
SISALTO_MAX = 12000  # montako merkkiä haetusta sivusta syötetään tiivistäjälle
# Selaimen User-Agent sivujen hakuun (jotkin sivut torjuvat oletus-urllibin).
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

# Yhden ajon hakutulosten välitallennus daily.py:n viereen tmp/-kansioon
# (.gitignoren 'tmp'-sääntö ohittaa). Jos lähetys epäonnistuu, tulokset jäävät
# tänne -> seuraava ajo käyttää niitä eikä kysy Staanilta uudestaan. Poistetaan
# onnistuneen ajon päätteeksi.
VALIAIKAKANSIO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tmp")
VALIAIKATIEDOSTO = os.path.join(VALIAIKAKANSIO, "tulokset.json")

# Lähetetyt uutiset arkistoidaan Obsidian-vaultiin muistiinpanoina (frontmatterin
# source-kenttä = URL). Tämä toimii samalla PYSYVÄNÄ dedup-lähteenä: jo
# tallennettuja URL:eja ei valita/tulkita uudestaan.
VAULT = os.environ.get("OBSIDIAN_VAULT_PATH", "/vault")
STAAN_KANSIO = os.path.join(VAULT, "Clippings", "Staan")

QUERIES = [
    "EU digital sovereignty local AI models foundation models infrastructure",
    "sovereign open source AI models France Germany Italy European",
    "European AI data sovereignty national infrastructure French",
    "Finland national AI strategy local language models government",
]


def loki(viesti):
    print(viesti, file=sys.stderr, flush=True)


def tallenna_valiaika(tulokset):
    os.makedirs(VALIAIKAKANSIO, exist_ok=True)
    with open(VALIAIKATIEDOSTO, "w") as f:
        json.dump(tulokset, f, ensure_ascii=False)


def lue_valiaika():
    # Palauttaa edellisen ajon tulokset, tai None jos tiedostoa ei ole / se on rikki.
    try:
        with open(VALIAIKATIEDOSTO) as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return None


def poista_valiaika():
    try:
        os.remove(VALIAIKATIEDOSTO)
    except FileNotFoundError:
        pass


def lue_lahetetyt():
    # Kerää jo arkistoitujen muistiinpanojen source-URL:t vaultista (dedup-lähde).
    urlit = set()
    try:
        tiedostot = os.listdir(STAAN_KANSIO)
    except FileNotFoundError:
        return urlit
    for nimi in tiedostot:
        if not nimi.endswith(".md"):
            continue
        try:
            with open(os.path.join(STAAN_KANSIO, nimi), encoding="utf-8") as f:
                for rivi in f:
                    if rivi.startswith("source:"):
                        urlit.add(rivi.split("source:", 1)[1].strip())
                        break
        except OSError:
            continue
    return urlit


def puhdista_nimi(teksti):
    # Tiedostonimeksi kelpaava versio otsikosta (vrt. download_transcript.sh).
    return re.sub(r"[^a-zA-Z0-9 _.,-]", "_", teksti).strip()[:120]


def tallenna_muistiinpano(valinta):
    # Arkistoi lähetetyn uutisen vaultiin (sama sisältö kuin Telegram-viestissä).
    # Toimii samalla dedup-merkintänä: tehdään heti onnistuneen lähetyksen jälkeen.
    os.makedirs(STAAN_KANSIO, exist_ok=True)
    nimi = puhdista_nimi(valinta["t"]) or hashlib.sha1(valinta["u"].encode()).hexdigest()[:12]
    sisalto = (
        "---\n"
        f"source: {valinta['u']}\n"
        f"pvm: {valinta['pvm']}\n"
        "---\n\n"
        f"# {valinta['t']}\n{valinta['runko']}\n\n"
        f"# Sitra\n{valinta['tulkinta']}\n"
    )
    with open(os.path.join(STAAN_KANSIO, f"{nimi}.md"), "w", encoding="utf-8") as f:
        f.write(sisalto)


def sivu_sallittu(url):
    # robots.txt: kunnioitetaan sivuston sääntöjä ("mikäli verkkosivu sallii").
    # Virhe / ei robots.txt:ää -> sallitaan (lenient).
    try:
        p = urlparse(url)
        robots = f"{p.scheme}://{p.netloc}/robots.txt"
        with urlopen(Request(robots, headers={"User-Agent": UA}), timeout=8) as r:
            rp = RobotFileParser()
            rp.parse(r.read().decode("utf-8", "replace").splitlines())
        return rp.can_fetch(UA, url)
    except Exception:
        return True


def hae_sivun_html(url):
    # Hakee sivun raa'an HTML:n, tai None jos sivu ei ole sallittu (robots), haku
    # epäonnistuu, tai sisältö ei ole HTML:ää.
    if not sivu_sallittu(url):
        loki(f"robots.txt estää haun: {url}")
        return None
    try:
        pyynto = Request(url, headers={"User-Agent": UA, "Accept-Language": "fi,en;q=0.8"})
        with urlopen(pyynto, timeout=20) as resp:
            if "html" not in resp.headers.get("Content-Type", "").lower():
                return None
            raaka = resp.read(2_000_000)  # katkaistaan 2 MB:hen
    except Exception as e:
        loki(f"Sivun haku epäonnistui ({url}): {e}")
        return None
    return raaka.decode("utf-8", "replace")


def html_tekstiksi(html):
    # Purkaa HTML:stä pelkän tekstin (script/style/kommentit/tagit pois).
    html = re.sub(r"(?is)<(script|style|noscript|template)\b.*?</\1>", " ", html)
    html = re.sub(r"(?s)<!--.*?-->", " ", html)
    teksti = unescape(re.sub(r"(?s)<[^>]+>", " ", html))
    teksti = re.sub(r"\s+", " ", teksti).strip()
    return teksti[:SISALTO_MAX] or None


def etsi_pvm(html):
    # Kaivaa artikkelin julkaisupäivän HTML:stä (JSON-LD datePublished, meta-tagit,
    # <time datetime>). Palauttaa muodon dd.mm.yy, tai None jos ei löydy.
    ehdokkaat = re.findall(r'"datePublished"\s*:\s*"([^"]+)"', html)
    nimet = r"article:published_time|datePublished|date|dc\.date|dcterms\.date|pubdate"
    ehdokkaat += re.findall(
        rf'<meta[^>]+(?:property|name|itemprop)=["\'](?:{nimet})["\'][^>]+content=["\']([^"\']+)["\']',
        html, re.I)
    ehdokkaat += re.findall(  # content ennen property/name -järjestys
        rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name|itemprop)=["\'](?:{nimet})["\']',
        html, re.I)
    ehdokkaat += re.findall(r'<time[^>]+datetime=["\']([^"\']+)["\']', html, re.I)
    for s in ehdokkaat:
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
        if m:
            v, kk, pp = m.groups()
            return f"{pp}.{kk}.{v[2:]}"
    return None


def tiivista_sisalto(teksti):
    # Suomenkielinen tiivistelmä haetusta sivun sisällöstä. Palauttaa None jos
    # epäonnistuu — tiivistelmä on lisäarvo eikä saa kaataa koko ajoa.
    prompt = (
        "Tiivistä seuraavan verkkosivun/uutisartikkelin sisältö SUOMEKSI 3-5 "
        "virkkeellä. Keskity olennaiseen asiasisältöön; ohita navigaatio, mainokset "
        "ja muu epäolennainen. Älä käytä markdown-muotoilua.\n\n"
        "SISÄLTÖ:\n" + teksti)
    payload = json.dumps({
        "model": MALLI_TEKSTIT, "prompt": prompt, "stream": False, "think": False,
    }).encode("utf-8")
    req = Request(OLLAMA_URL, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=OLLAMA_AIKAKATKAISU) as resp:
            vastaus = json.load(resp).get("response", "").strip()
    except Exception as e:
        loki(f"Sisällön tiivistys epäonnistui: {e}")
        return None
    return riisu_markdown(vastaus).strip() or None


def haetaan(query):
    if not KEY:
        loki("STAAN_API_KEY puuttuu — ohitetaan haku.")
        return []
    url = f"https://api.staan.ai/v2/search/web?q={quote(query)}"
    req = Request(url, method="GET")
    req.add_header("Authorization", f"Bearer {KEY}")
    try:
        with urlopen(req, timeout=15) as resp:
            data = json.load(resp)
    except Exception as e:
        loki(f"Haku epäonnistui ({query[:40]!r}): {e}")
        return []
    items = data.get("web", {}).get("results", [])
    tulokset = []
    for r in items[:LIMIT]:
        osoite = r.get("url")
        if not osoite:
            continue
        tulokset.append({"t": r.get("title", ""), "u": osoite, "s": r.get("snippet", "")})
    return tulokset


def yhdista():
    kaikki = []
    for q in QUERIES:
        kaikki += haetaan(q)
    nakyvat = set()
    yks = []
    for r in kaikki:
        if r["u"] not in nakyvat:
            nakyvat.add(r["u"])
            yks.append(r)
    return yks   # kaikki uniikit; karsinta (vault) ja rajaus tehdään mainissa


def valitse_uutiset(tulokset):
    # Valitsee mallilla enintään VALINTOJA relevanteinta uutista (vain valinta;
    # tiivistelmä ja tulkinta tehdään myöhemmin sivun sisällön pohjalta).
    # Palauttaa valitut raakatulokset {"t","u","s"} datasta (indeksin kautta).
    if not tulokset:
        return []
    numeroidut = "\n\n".join(
        f"[{i}] {r['t']}\n{r['u']}\n{r['s']}" for i, r in enumerate(tulokset))
    prompt = (
        "Olet EU:n digitaalista suvereniteettia seuraava analyytikko Sitralla.\n\n"
        f"Valitse alla olevista uutisista ENINTÄÄN {VALINTOJA} relevanteinta EU:n "
        "digitaalisen suvereniteetin ja PAIKALLISTEN tekoälymallien kannalta, Suomen "
        "ja Sitran näkökulmasta.\n\n"
        'Palauta pelkkä JSON: {"valinnat": [{"indeksi": <hakasulkeissa oleva numero>}]}\n\n'
        "UUTISET:\n" + numeroidut)
    payload = json.dumps({
        "model": MALLI_TEKSTIT,
        "prompt": prompt,
        "stream": False,
        "think": False,    # päättelymalli: ohitetaan "ajattelu" -> nopea vastaus
        "format": "json",  # pakota validi JSON -> luotettava jäsennys
    }).encode("utf-8")
    req = Request(OLLAMA_URL, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=OLLAMA_AIKAKATKAISU) as resp:
            vastaus = json.load(resp).get("response", "").strip()
    except Exception as e:
        # Nostetaan poikkeus -> ajo epäonnistuu, välitiedosto säilyy uusintaa varten.
        loki(f"Ollama epäonnistui: {e}")
        raise
    try:
        valinnat = json.loads(vastaus).get("valinnat", [])
    except ValueError:
        raise RuntimeError(f"Mallin vastaus ei ollut validia JSONia: {vastaus[:200]!r}")

    valitut = []
    nahdyt = set()
    for v in valinnat:
        try:
            i = int(v.get("indeksi"))
        except (TypeError, ValueError):
            continue
        if not (0 <= i < len(tulokset)) or i in nahdyt:
            continue
        nahdyt.add(i)
        valitut.append(tulokset[i])
        if len(valitut) >= VALINTOJA:
            break
    return valitut


def tee_tulkinta(otsikko, sisalto):
    # Sitra-näkökulma uutisen SISÄLLÖN (tiivistelmä tai snippetti) pohjalta.
    # Nostaa poikkeuksen Ollama-virheessä (ydinosa viestiä).
    prompt = (
        "Olet EU:n digitaalista suvereniteettia ja paikallisia tekoälymalleja "
        "seuraava analyytikko Sitralla. Alla on uutisen tiivistelmä. Kirjoita "
        "SUOMEKSI 2-3 konkreettista virkettä siitä, miten Sitra voi olla avuksi tai "
        "mitä mahdollisuus tarkoittaa Suomelle. Älä käytä markdown-muotoilua.\n\n"
        f"OTSIKKO: {otsikko}\n\nTIIVISTELMÄ:\n{sisalto}")
    payload = json.dumps({
        "model": MALLI_TEKSTIT, "prompt": prompt, "stream": False, "think": False,
    }).encode("utf-8")
    req = Request(OLLAMA_URL, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=OLLAMA_AIKAKATKAISU) as resp:
            vastaus = json.load(resp).get("response", "").strip()
    except Exception as e:
        loki(f"Tulkinnan teko epäonnistui: {e}")
        raise
    tulkinta = riisu_markdown(vastaus).strip()
    if not tulkinta:
        raise RuntimeError("Malli palautti tyhjän tulkinnan.")
    return tulkinta


def muotoile(valinta):
    # Yksi Telegram-viesti: otsikko + sisällön tiivistelmä, Sitra-tulkinta, lähde
    # (julkaisupäivä suluissa).
    return (
        f"# {valinta['t']}\n{valinta['runko']}\n\n"
        f"# Sitra\n{valinta['tulkinta']}\n\n"
        f"Lähde ({valinta['pvm']}):\n{valinta['u']}"
    )


def laheta(viesti):
    # --raaka: viesti on jo siivottu (rungon #-otsikot halutaan säilyttää).
    laheta_skripti = os.path.join(TELEGRAM_DIR, "laheta.py")
    subprocess.run([sys.executable, laheta_skripti, "--raaka", viesti], check=True)


def main():
    print(f"[{date.today()}] EU DS Daily:")
    # Käytä edellisen epäonnistuneen ajon tuloksia jos ne ovat tallessa,
    # muuten hae Staanista ja tallenna ne (jos tuloksia löytyi).
    tulos = lue_valiaika()
    if tulos:
        print(f"Käytetään edellisen ajon välitallenteita: {len(tulos)} tulosta")
    else:
        tulos = yhdista()
        print(f"Tuloksia: {len(tulos)}")
        if tulos:
            tallenna_valiaika(tulos)

    # Karsi jo vaultiin arkistoidut pois ENNEN rajausta, jotteivät jo lähetetyt
    # vie ehdokaspaikkoja tuoreilta (näin myös myöhempien hakutermien tulokset
    # pääsevät mukaan kun aiemmat on jo lähetetty).
    lahetetyt = lue_lahetetyt()
    tuoreet = [r for r in tulos if r["u"] not in lahetetyt]
    print(f"Uusia (ei aiemmin lähetettyjä): {len(tuoreet)}/{len(tulos)}")
    if not tuoreet:
        print("Ei uusia uutisia — ei lähetetä.")
        poista_valiaika()
        return

    uudet = tuoreet[:LIMIT]   # rajaa mallille tarjottava ehdokasjoukko vasta nyt
    pvm = date.today().strftime("%d.%m.%y")
    valinnat = valitse_uutiset(uudet)
    if not valinnat:
        print("Malli ei valinnut yhtään uutista.")
        poista_valiaika()
        return

    # Jokaiselle valitulle: 1) lue sivu ja tee tiivistelmä, 2) tulkitse Sitran
    # rooli sisällön pohjalta, 3) lähetä Telegramiin, 4) arkistoi vaultiin
    # (dedup-merkintä). Merkitään lähetetyksi vasta onnistuneen lähetyksen jälkeen.
    for r in valinnat:
        html = hae_sivun_html(r["u"])
        sisalto = html_tekstiksi(html) if html else None
        tiivistelma = tiivista_sisalto(sisalto) if sisalto else None
        runko = tiivistelma or r["s"]          # sivun tiivistelmä, fallback snippettiin
        tulkinta = tee_tulkinta(r["t"], runko)  # Sitra-näkökulma sisällön pohjalta
        # Julkaisupäivä sisällöstä; fallback hakupäivään jos ei löydy.
        julkaisu_pvm = (etsi_pvm(html) if html else None) or pvm
        valinta = {"t": r["t"], "u": r["u"], "runko": runko,
                   "tulkinta": tulkinta, "pvm": julkaisu_pvm}
        laheta(muotoile(valinta))
        tallenna_muistiinpano(valinta)
        print(f"Lähetetty: {r['t'][:60]} (pvm: {julkaisu_pvm}, sisältö: {'kyllä' if tiivistelma else 'snippet'})")

    poista_valiaika()
    print(f"[OK] Lähetetty {len(valinnat)} viestiä")


if __name__ == "__main__":
    main()
