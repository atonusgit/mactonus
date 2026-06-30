#!/usr/bin/env python3
# Telegram-silta pi-botille.
#
# pi:ssä ei ole hermesin kaltaista gateway-tilaa, joten tämä prosessi toimii
# siltana: kuuntelee Telegramia long-pollauksella ja ajaa jokaista viestiä
# varten pi:n headless-tilassa (`pi --mode json`). Keskustelukonteksti säilyy
# per chat `--session-id`-lipulla (pi luo session jos sitä ei ole ja jatkaa
# olemassa olevaa). Vastaus poimitaan JSON-tapahtumavirran message_end:istä ja
# lähetetään takaisin Telegramiin.
#
# HUOM pi-versio: tämä olettaa npm:n @earendil-works/pi-coding-agent -pi:n.
# Vanha `pi -p` (text) korvattiin `--mode json`:lla (ks. pi.dev/docs/latest/json),
# koska se antaa rakenteisen, luotettavasti jäsennettävän tulosteen.
#
# TURVA: pi voi ajaa bashia ja kirjoittaa /vault:iin, joten vain
# TELEGRAM_SALLITUT_CHATIT-listan chatit pääsevät läpi. Ilman listaa silta ei
# käynnisty.
#
# Ympäristömuuttujat (.env):
#   TELEGRAM_BOT_TOKEN        @BotFatherin antama token (pakollinen)
#   TELEGRAM_SALLITUT_CHATIT  sallitut chat-id:t pilkulla erotettuna (pakollinen)
#   PI_TYOHAKEMISTO           pi:n työhakemisto (oletus /vault)
#   PI_AIKAKATKAISU           yhden vastauksen aikaraja sekunteina (oletus 600)
#   PI_MALLI                  pakota malli `--model`-lipulla (oletus: tyhjä = pi
#                             valitsee models.json:n ainoan mallin)

import html, json, os, re, sys, time, signal, subprocess, threading
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from telegram_api import api_kutsu, laheta_viesti, riisu_markdown

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
SALLITUT = {c.strip() for c in os.environ.get("TELEGRAM_SALLITUT_CHATIT", "").split(",") if c.strip()}
PI_TYOHAKEMISTO = os.environ.get("PI_TYOHAKEMISTO", "/vault")
PI_AIKAKATKAISU = int(os.environ.get("PI_AIKAKATKAISU", "600"))
PI_MALLI = os.environ.get("PI_MALLI", "").strip()

# Telegram-viestit, jotka aloittavat uuden keskustelun (tuore pi-session-id).
NOLLAUS_KOMENNOT = {"/uusi", "/reset", "/nollaa", "uusi keskustelu"}
# Per-chat session-suffiksi tallennetaan tähän; suffiksin kasvatus = uusi sessio.
SUFFIKSI_TIEDOSTO = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "sessio_suffiksit.json")


# Per-chat keskustelu pidetään erillään session-id:llä. Suffiksi mahdollistaa
# "uuden keskustelun" Telegramista: NOLLAUS_KOMENNOT kasvattaa suffiksia, jolloin
# seuraava viesti saa tuoreen session-id:n -> pi luo uuden session ja lukee mm.
# skill-katalogin uudelleen. `--session-id` luo session jos sitä ei ole ja jatkaa
# olemassa olevaa.
def _lue_suffiksit():
    try:
        with open(SUFFIKSI_TIEDOSTO, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {}


def _tallenna_suffiksit(suffiksit):
    # Atominen kirjoitus (temp + rename), jottei tiedosto korruptoidu.
    tmp = f"{SUFFIKSI_TIEDOSTO}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(suffiksit, f, ensure_ascii=False, indent=2)
    os.replace(tmp, SUFFIKSI_TIEDOSTO)


def nollaa_sessio(chat_id):
    # Kasvata chatin suffiksia -> seuraava viesti aloittaa tuoreen session.
    suffiksit = _lue_suffiksit()
    suffiksit[chat_id] = int(suffiksit.get(chat_id, 1)) + 1
    _tallenna_suffiksit(suffiksit)
    return suffiksit[chat_id]


def sessio_id(chat_id):
    suffiksi = _lue_suffiksit().get(chat_id, 1)
    return f"tg-{chat_id}-{suffiksi}"

# YouTube-linkin tunnistus viestistä. Jos linkki löytyy, silta lataa sen
# transkription deterministisesti download_transcript.sh:lla ENNEN kuin viesti
# menee pi:lle (ks. lataa_transkriptio). Polku selvitetään tämän tiedoston
# sijainnista, joten se toimii myös kontin ulkopuolella.
YOUTUBE_RE = re.compile(
    r"https?://(?:www\.|m\.)?(?:youtube\.com/(?:watch\?\S*v=|shorts/|live/)|youtu\.be/)[\w\-]+\S*"
)
_SKRIPTIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LATAA_SKRIPTI = os.path.join(_SKRIPTIT, "youtube", "download_transcript.sh")
# Sisältää litteroinnin haun JA suomenkielisen tiivistyksen (Mistral) -> reilumpi raja.
LATAUS_AIKAKATKAISU = int(os.environ.get("YOUTUBE_AIKAKATKAISU", "600"))
# YouTube-litterointi on oletuksena päällä. Voidaan kytkeä pois esim.
# vaultittomassa kontissa (YOUTUBE_LATAUS=0), jolloin linkkejä ei käsitellä.
YOUTUBE_LATAUS = os.environ.get("YOUTUBE_LATAUS", "1").strip().lower() not in ("0", "false", "ei", "no")

# Muiden (ei-YouTube) http(s)-linkkien tunnistus. Silta tarkistaa robots.txt:n, hakee
# sivun, tiivistää sen (Mistral) ja tallentaa Clippings/Verkkosivutiivistelmät/:iin
# deterministisesti ENNEN kuin viesti menee pi:lle (ks. tallenna_verkkosivu).
VERKKOSIVU_RE = re.compile(r"https?://[^\s]+")
VERKKOSIVU_SKRIPTI = os.path.join(_SKRIPTIT, "verkkosivu", "tallenna_verkkosivu.py")
# PDF-linkit (URL:n polku päättyy .pdf) reititetään suoraan pdf-skriptille — muuten ne
# menisivät verkkosivu-skraperille, joka kaatuu PDF:ään. tallenna_pdf.py lataa PDF:n ja
# merkitsee URL:n lähteeksi.
PDF_SKRIPTI = os.path.join(_SKRIPTIT, "pdf", "tallenna_pdf.py")
# Oletuksena päällä; kytke pois VERKKOSIVU_TALLENNUS=0 (esim. vaultittomassa kontissa).
VERKKOSIVU_TALLENNUS = os.environ.get("VERKKOSIVU_TALLENNUS", "1").strip().lower() not in ("0", "false", "ei", "no")
# Kun päällä, silta liittää viestin alkuun lähettäjän nimen/käyttäjätunnuksen/id:n,
# jotta pi tietää KENEN kanssa puhuu (monikäyttäjäidentiteetit, esim. Närhisulka).
# Oletuksena pois -> yhden käyttäjän identiteetit (esim. mactonus) ennallaan.
KERRO_LAHETTAJA = os.environ.get("KERRO_LAHETTAJA", "0").strip().lower() in ("1", "true", "kyllä", "yes")
# Kun päällä (oletus), silta ilmoittaa Telegramiin jokaisesta pi:n työkalukutsusta
# heti sen alkaessa (tool_execution_start). Vaimennettavissa KERRO_TYOKALUT=0.
KERRO_TYOKALUT = os.environ.get("KERRO_TYOKALUT", "1").strip().lower() not in ("0", "false", "ei", "no")


def loki(viesti):
    print(viesti, flush=True)


def lahettaja_tunniste(viesti):
    # Rakentaa pi:lle annettavan rivin viestin lähettäjästä, esim.
    # "[Viesti käyttäjältä Anton Valle (@anton), id 123]". Tyhjä jos tieto puuttuu.
    lahettaja = viesti.get("from") or {}
    nimi = " ".join(x for x in (lahettaja.get("first_name"), lahettaja.get("last_name")) if x)
    tunnus = lahettaja.get("username")
    kid = lahettaja.get("id")
    osat = [nimi or "tuntematon"]
    if tunnus:
        osat.append(f"(@{tunnus})")
    if kid is not None:
        osat.append(f"id {kid}")
    return f"[Viesti käyttäjältä {' '.join(osat)}]"


def naytä_kirjoittaa(chat_id):
    try:
        api_kutsu("sendChatAction", {"chat_id": chat_id, "action": "typing"})
    except Exception:
        pass


def aja_url_skripti(komento, url, aikakatkaisu, nimi):
    # Ajaa lataus-/tallennusskriptin annetulla linkillä ja palauttaa luodun tiedoston
    # polun, tai None jos epäonnistui. Skriptit tulostavat onnistuessaan "Saved to: <polku>".
    try:
        tulos = subprocess.run(
            komento + [url],
            cwd=PI_TYOHAKEMISTO,
            capture_output=True, text=True, timeout=aikakatkaisu,
        )
    except subprocess.TimeoutExpired:
        loki(f"{nimi} aikakatkaistiin: {url}")
        return None
    except FileNotFoundError:
        loki(f"Virhe: {nimi} -skriptiä ei löydy.")
        return None
    for rivi in (tulos.stdout or "").splitlines():
        if rivi.startswith("Saved to:"):
            return rivi.split("Saved to:", 1)[1].strip()
    loki(f"{nimi} ei tuottanut tiedostoa ({url}): {(tulos.stdout or tulos.stderr or '').strip()[:200]}")
    return None


def esikasittele(teksti):
    # Jos viestissä on linkki, käsitellään se deterministisesti (YouTube -> litterointi,
    # .pdf-URL -> PDF-tiivistelmä, muu http(s) -> verkkosivutiivistelmä) ja kerrotaan pi:lle
    # tiedostopolku (ei sisältöä -> ei kontek-ikkunan räjäytystä). Palauttaa pi:lle annettavan tekstin.
    if YOUTUBE_LATAUS:
        osuma = YOUTUBE_RE.search(teksti)
        if osuma:
            url = osuma.group(0)
            loki(f"YouTube-linkki havaittu, ladataan transkriptio: {url}")
            polku = aja_url_skripti(["bash", LATAA_SKRIPTI], url, LATAUS_AIKAKATKAISU,
                                    "YouTube-litterointi")
            if polku:
                ohje = (f"[Järjestelmä: viestin YouTube-video on jo litteroitu tiedostoon "
                        f"{polku}. Lue se read-työkalulla, jos vastaus sitä edellyttää.]")
            else:
                ohje = ("[Järjestelmä: viestin YouTube-linkin litterointi epäonnistui — "
                        "transkriptiota ei ole saatavilla.]")
            return f"{ohje}\n\n{teksti}"

    if VERKKOSIVU_TALLENNUS:
        osuma = VERKKOSIVU_RE.search(teksti)
        if osuma:
            url = osuma.group(0)
            if urlparse(url).path.lower().endswith(".pdf"):
                loki(f"PDF-linkki havaittu, tallennetaan tiivistelmä: {url}")
                polku = aja_url_skripti(["python3", PDF_SKRIPTI], url, LATAUS_AIKAKATKAISU,
                                        "PDF-tiivistelmä")
                if polku:
                    ohje = (f"[Järjestelmä: viestin PDF on jo haettu ja tiivistetty tiedostoon "
                            f"{polku}. Lue se read-työkalulla, jos vastaus sitä edellyttää.]")
                else:
                    ohje = ("[Järjestelmä: viestin PDF-linkin tallennus epäonnistui "
                            "(lataus/tiivistys ei onnistunut, tai PDF oli skannattu).]")
                return f"{ohje}\n\n{teksti}"
            loki(f"Verkkosivulinkki havaittu, tallennetaan tiivistelmä: {url}")
            polku = aja_url_skripti(["python3", VERKKOSIVU_SKRIPTI], url, LATAUS_AIKAKATKAISU,
                                    "Verkkosivutiivistelmä")
            if polku:
                ohje = (f"[Järjestelmä: viestin verkkosivu on jo haettu ja tiivistetty tiedostoon "
                        f"{polku}. Lue se read-työkalulla, jos vastaus sitä edellyttää.]")
            else:
                ohje = ("[Järjestelmä: viestin verkkosivun tallennus epäonnistui "
                        "(robots.txt esti, haku ei onnistunut tai sisältöä ei ollut).]")
            return f"{ohje}\n\n{teksti}"

    return teksti


def muotoile_tyokalu(toolName, args):
    # Kaksirivinen, ihmisluettava ilmoitus Telegramiin (parse_mode=HTML):
    #   🔧 Käytän työkalua
    #   <code>varsinainen tieto monospacena</code>
    # Jos työkalulla ei ole selkeää dataa, näytetään nimi otsikkorivillä.
    detalji = ""
    if isinstance(args, dict):
        for avain in ("command", "path", "file_path", "url", "pattern", "query"):
            if args.get(avain):
                detalji = str(args[avain])
                break
        else:
            for arvo in args.values():
                if arvo not in (None, "", [], {}):
                    detalji = str(arvo)
                    break
    if detalji:
        detalji = " ".join(detalji.split())
        if len(detalji) > 200:
            detalji = detalji[:199] + "…"
        return f"🔧 Käytän työkalua\n<code>{html.escape(detalji)}</code>"
    return (f"🔧 Käytän työkalua ({html.escape(toolName)})" if toolName
            else "🔧 Käytän työkalua")


def aja_pi(chat_id, teksti):
    # --session-id pitää tämän chatin keskustelun erillään ja jatkaa sitä
    # (luodaan jos puuttuu). --mode json antaa rakenteisen JSONL-tapahtumavirran,
    # joka luetaan rivi kerrallaan (striimaus), jotta työkalukutsut voidaan
    # ilmoittaa Telegramiin heti niiden alkaessa (tool_execution_start). Lopullinen
    # vastaus poimitaan viimeisen assistant-roolisen message_end-tapahtuman teksteistä.
    komento = ["pi", "--mode", "json", "--session-id", sessio_id(chat_id)]
    if PI_MALLI:
        komento += ["--model", PI_MALLI]
    komento += [teksti]

    try:
        proc = subprocess.Popen(
            komento, cwd=PI_TYOHAKEMISTO,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, start_new_session=True,
        )
    except FileNotFoundError:
        return "Virhe: pi-komentoa ei löydy kontista."

    # Aikakatkaisu: tapa koko prosessiryhmä (pi + sen lapsiprosessit), jotta
    # stdout-putki sulkeutuu heti ja lukusilmukka vapautuu. Pelkkä proc.kill()
    # ei riittäisi, koska lapsenlapset pitäisivät putken auki.
    tila = {"aikakatkaistu": False}

    def _tapa():
        tila["aikakatkaistu"] = True
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            proc.kill()

    vahti = threading.Timer(PI_AIKAKATKAISU, _tapa)
    vahti.start()

    vastaus, virhe, rivit = None, None, []
    try:
        for rivi in proc.stdout:
            rivit.append(rivi)
            rivi = rivi.strip()
            if not rivi:
                continue
            try:
                tapahtuma = json.loads(rivi)
            except ValueError:
                continue  # ei-JSON-roska (esim. stderr-varoitus)
            tyyppi = tapahtuma.get("type")
            if tyyppi == "tool_execution_start":
                if KERRO_TYOKALUT:
                    args = tapahtuma.get("args", tapahtuma.get("arguments"))
                    laheta_viesti(chat_id,
                                  muotoile_tyokalu(tapahtuma.get("toolName"), args),
                                  loki=loki, parse_mode="HTML")
            elif tyyppi == "message_end":
                viesti = tapahtuma.get("message") or {}
                if viesti.get("role") != "assistant":
                    continue
                if viesti.get("stopReason") in ("error", "aborted"):
                    virhe = viesti.get("errorMessage") or f"pyyntö {viesti.get('stopReason')}"
                    vastaus = None
                    continue
                osat = [c.get("text", "") for c in (viesti.get("content") or [])
                        if c.get("type") == "text"]
                koottu = "".join(osat).strip()
                if koottu:
                    vastaus, virhe = koottu, None
    finally:
        vahti.cancel()
    rc = proc.wait()

    if tila["aikakatkaistu"]:
        return "Vastaus aikakatkaistiin (malli oli liian hidas)."
    if rc != 0 or virhe:
        häntä = "".join(rivit).strip()[-500:]
        loki(f"pi virhe (rc={rc}): {virhe or häntä}")
        return vastaus or f"pi epäonnistui: {(virhe or häntä)[:500]}"
    return vastaus or "(pi ei palauttanut tekstiä)"


def main():
    if not TOKEN:
        sys.exit("TELEGRAM_BOT_TOKEN puuttuu .env:stä.")
    if not SALLITUT:
        sys.exit("TELEGRAM_SALLITUT_CHATIT puuttuu .env:stä (pakollinen turvasyistä).")
    loki(f"Telegram-silta käynnistyy. Sallitut chatit: {sorted(SALLITUT)}")

    # Tyhjennä backlog käynnistyksessä: ohita ennen käynnistystä tulleet viestit.
    offset = None
    try:
        alku = api_kutsu("getUpdates", {"timeout": 0})
        if alku.get("result"):
            offset = alku["result"][-1]["update_id"] + 1
    except Exception as e:
        loki(f"Backlogin tyhjennys epäonnistui: {e}")

    while True:
        try:
            data = {"timeout": 30}
            if offset is not None:
                data["offset"] = offset
            vastaus = api_kutsu("getUpdates", data, timeout=40)
        except Exception as e:
            loki(f"getUpdates epäonnistui: {e}")
            time.sleep(5)
            continue

        for upd in vastaus.get("result", []):
            offset = upd["update_id"] + 1
            viesti = upd.get("message") or upd.get("edited_message")
            if not viesti:
                continue
            chat_id = str(viesti.get("chat", {}).get("id", ""))
            teksti = viesti.get("text", "")
            if chat_id not in SALLITUT:
                loki(f"Estetty chat {chat_id}: {teksti[:50]!r}")
                laheta_viesti(chat_id, "Ei käyttöoikeutta.", loki=loki)
                continue
            if not teksti:
                # Teksitön viesti = liite (document/photo/voice/…). Liitteitä ei vielä
                # käsitellä, joten kerrotaan se käyttäjälle hiljaisen ohituksen sijaan.
                loki(f"Teksitön viesti chatissa {chat_id} (liite?) — ei käsitellä.")
                laheta_viesti(chat_id, "En lue liitteitä tällä hetkellä — lähetä viestisi tekstinä tai linkkinä.", loki=loki)
                continue
            if teksti.strip().lower() in NOLLAUS_KOMENNOT:
                suffiksi = nollaa_sessio(chat_id)
                loki(f"Sessio nollattu chatille {chat_id} -> suffiksi {suffiksi}")
                laheta_viesti(chat_id, "🆕 Aloitettu uusi keskustelu.", loki=loki)
                continue
            loki(f"Viesti {chat_id}: {teksti[:80]!r}")
            naytä_kirjoittaa(chat_id)
            teksti_pi = esikasittele(teksti)
            if KERRO_LAHETTAJA:
                teksti_pi = f"{lahettaja_tunniste(viesti)}\n\n{teksti_pi}"
            laheta_viesti(chat_id, riisu_markdown(aja_pi(chat_id, teksti_pi)), loki=loki)


if __name__ == "__main__":
    main()
