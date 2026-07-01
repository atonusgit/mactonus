#!/usr/bin/env python3
"""Katkaiseva proxy pi:n ja llama.cpp:n väliin.

llama.cpp ei tarkoituksella katkaise liian isoa promptia — se hylkää 400:lla
(exceed_context_size_error) toisin kuin Ollama joka katkaisi hiljaa
palvelinpuolella (ggml-org/llama.cpp#17284). Tämä proxy lisää sen puuttuvan
kerroksen. Se:

- kun prompti ylittää YLA_OSUUS (oletus 70%) ikkunasta, kompaktoi kunnes se on
  alle ALA_OSUUS (oletus 40%): tiivistää vanhimman tekstiviestin ~3 lauseeseen
  (rullaava tiivistys, cachettu) tai pudottaa sen; system- ja nykyinen viesti
  säilyvät. Hystereesi -> tiivistys ei aja joka pyynnöllä, ja alarajaan jää tilaa
  vastaukselle,
- kirjoittaa vastauksen finish_reason "length" -> "stop", jottei pi näytä
  katkennutta vastausta virheenä ("maximum output token limit"),
- striimaa SSE:n rivi kerrallaan ja päättää sen siististi ([DONE]/EOF/idle),
  ettei pi jäätyy,
- varaverkkona: jos ylävirta silti palauttaa 400:n, pudottaa vanhinta ja yrittää
  uudelleen kunnes prompti mahtuu.

Ajetaan mactonus-kontin sisällä (skriptit mountattu /root/scripts:iin) pi:n
rinnalle. pi osoittaa localhostiin :8081, proxy välittää hostin llama.cpp:hen:
    docker exec -it mactonus python3 /root/scripts/kompaktointi_valipalvelin.py
Env: YLAVIRTA=host.docker.internal:8080 PORTTI=8081 AIKAKATKAISU=120 KERROIN=1.5
     YLA_OSUUS=0.7 ALA_OSUUS=0.4 TIIVISTA=1 TIIVISTE_MIN=200 KONTEKSTI=(ohittaa /props:n)
(hostilla ajettaessa aseta YLAVIRTA=127.0.0.1:8080)
"""
import hashlib, json, os, socket, sys, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Oletus kontista: llama.cpp on hostilla host.docker.internal:8080.
YLAVIRTA = os.environ.get("YLAVIRTA", "host.docker.internal:8080")
PORTTI = int(os.environ.get("PORTTI", "8081"))
# Idle-timeout: kuinka kauan odotetaan seuraavaa dataa ennen kuin striimi
# katsotaan pysähtyneeksi. Rajaa jäätymisen (ylävirta ei sulje eikä lähetä).
AIKAKATKAISU = int(os.environ.get("AIKAKATKAISU", "120"))
# Hystereesi: kompaktointi KÄYNNISTYY kun prompti ylittää YLA_OSUUS ikkunasta, ja
# jatkuu kunnes prompti on alle ALA_OSUUS. Kaksi kynnystä (ei yksi) välttää sen
# että tiivistys ajaisi joka pyynnöllä: iso pudotus alarajaan antaa pelivaraa
# usealle vuorolle ennen seuraavaa laukaisua. ALA jättää myös tilaa vastaukselle
# + pelivaraa (tokenilasku aliarvioi ~1,5x).
YLA_OSUUS = float(os.environ.get("YLA_OSUUS", "0.7"))   # laukaisukynnys
ALA_OSUUS = float(os.environ.get("ALA_OSUUS", "0.4"))   # kohde johon kompaktoidaan
# Varakerroin: kun tarkkaa /apply-template-laskentaa ei ole käytettävissä, promptin
# arvio lasketaan pelkästä sisällöstä (jättää chat-templaten + tool-boilerplaten
# huomiotta -> aliarvioi ~1,5x). Kerrotaan tällä, ettei kompaktointi jää laukeamatta.
KERROIN = float(os.environ.get("KERROIN", "1.5"))
_tarkka_laskenta = None   # None=ei tiedossa; True/False kun selviää (logataan kerran)
_KONTEKSTI = None  # n_ctx, haetaan llama.cpp /props:sta ensimmäisellä tarpeella

# Rullaava tiivistys: vanhin viesti tiivistetään 3 lauseeseen pudottamisen sijaan.
# TIIVISTA=0 palaa pelkkään pudotukseen. Tiivistelmät cachetaan sisällön hashilla,
# joten kukin vanha viesti tiivistetään vain kerran (pi lähettää alkuperäiset joka
# pyynnöllä -> ilman cachea tiivistettäisiin uudelleen joka kerta).
TIIVISTA = os.environ.get("TIIVISTA", "1") != "0"
TIIVISTE_PREFIX = "[tiivistelmä] "   # merkitsee jo tiivistetyn -> ei tiivistetä uudelleen
TIIVISTE_MIN = int(os.environ.get("TIIVISTE_MIN", "200"))  # lyhyempää ei kannata tiivistää
_tiivistelmat = {}   # sha1(sisältö) -> tiivistelmä (tai None jos tiivistys epäonnistui)

# Otsakkeet joita ei välitetä sellaisenaan: yhteyskohtaiset, uudelleenlasketut,
# sekä server/date jotka http.server lisää itse (muuten kahdentuisivat ja tiukka
# asiakas voi jumiutua).
OHITA_OTSAKKEET = {"host", "content-length", "connection", "transfer-encoding",
                   "server", "date"}


def _puolita_sisalto(viesti):
    """Puolittaa viestin sisällön säilyttäen LOPUN (tuorein/kysymys jää).
    Palauttaa True jos jotain kutistui. Käsittelee sekä str- että
    multimodaalisen (osalista) contentin."""
    sis = viesti.get("content")
    if isinstance(sis, str):
        if len(sis) <= 1:
            return False
        viesti["content"] = sis[len(sis) // 2:]
        return True
    if isinstance(sis, list):
        muuttui = False
        for osa in sis:
            t = osa.get("text")
            if isinstance(t, str) and len(t) > 1:
                osa["text"] = t[len(t) // 2:]
                muuttui = True
        return muuttui
    return False


def korjaa_length(data):
    """Kirjoittaa vastauksen finish_reason "length" -> "stop". Kun malli katkeaa
    token-budjettiin, pi näyttää sen VIRHEENÄ ("maximum output token limit").
    Muutos "stop":iin saa pi:n hyväksymään katkenneen (degradoituneen) vastauksen
    normaalisti — huono vastaus > ei vastausta. Kattaa molemmat välilyöntimuodot."""
    return (data.replace(b'"finish_reason":"length"', b'"finish_reason":"stop"')
                .replace(b'"finish_reason": "length"', b'"finish_reason": "stop"'))


def pudota_vanhin(runko):
    """Kutistaa promptia yhden askeleen. Palauttaa True jos jotain kutistui,
    False jos ei ole enää mitään kutistettavaa (jolloin 400 päästetään läpi).

    - >1 ei-system-viestiä: poista vanhin ei-system-viesti (system säilyy aina).
    - täsmälleen 1 ei-system-viesti (esim. iso tiedostoluku): puolita sen sisältö.
    """
    viestit = runko.get("messages")
    if not isinstance(viestit, list):
        return False
    ei_system = [i for i, v in enumerate(viestit) if v.get("role") != "system"]
    if len(ei_system) > 1:
        del viestit[ei_system[0]]
        return True
    if len(ei_system) == 1:
        return _puolita_sisalto(viestit[ei_system[0]])
    return False


def _hae_konteksti():
    """llama.cpp:n n_ctx. Env KONTEKSTI ohittaa; muuten /props; fallback 32768."""
    global _KONTEKSTI
    if _KONTEKSTI is not None:
        return _KONTEKSTI
    ymp = os.environ.get("KONTEKSTI")
    if ymp:
        _KONTEKSTI = int(ymp)
        return _KONTEKSTI
    try:
        with urllib.request.urlopen(f"http://{YLAVIRTA}/props", timeout=10) as r:
            d = json.loads(r.read().decode())
        print(f"[kompaktointi] /props: {json.dumps(d)[:600]}",
              file=sys.stderr, flush=True)
        g = d.get("default_generation_settings", {})
        # PER-SLOTIN konteksti: llama serve jakaa -c:n rinnakkaisslotteihin, joten
        # per-pyyntö saa vain n_ctx / n_parallel. Käytä per-seq-kenttää jos on,
        # muuten jaa n_ctx rinnakkaisuudella.
        n_total = int(g.get("n_ctx") or d.get("n_ctx") or 32768)
        n_par = int(d.get("n_parallel") or g.get("n_parallel") or 1)
        _KONTEKSTI = int(g.get("n_ctx_per_seq") or d.get("n_ctx_per_seq")
                         or (n_total // max(1, n_par)))
        print(f"[kompaktointi] per-slot konteksti = {_KONTEKSTI} "
              f"(n_ctx={n_total}, n_parallel={n_par})", file=sys.stderr, flush=True)
    except Exception as e:
        print(f"[kompaktointi] /props epäonnistui ({e}), oletus 32768",
              file=sys.stderr, flush=True)
        _KONTEKSTI = 32768
    return _KONTEKSTI


def _kokoa_teksti(runko):
    """Kaikki mikä menee promptiin -> tokenoinnin syötteeksi. HUOM: tools/functions
    -skeemat ovat osa oikeaa promptia (isot koodausagentilla) vaikka eivät
    messages-contentissa -> otetaan raakana JSONina, muuten prompti aliarvioidaan."""
    osat = []
    for v in runko.get("messages", []):
        sis = v.get("content")
        if isinstance(sis, str):
            osat.append(sis)
        elif isinstance(sis, list):
            osat += [o["text"] for o in sis if isinstance(o.get("text"), str)]
    for avain in ("tools", "functions"):   # skeemat ovat osa oikeaa promptia
        if runko.get(avain):
            osat.append(json.dumps(runko[avain]))
    return "\n".join(osat)


def _tokenoi(teksti, malli):
    """Tekstin tokenimäärä /tokenize:lla. None jos ei saatu. Tämä llama serve
    vaatii myös model-kentän -> välitetään chat-pyynnön malli."""
    try:
        data = json.dumps({"content": teksti, "model": malli}).encode()
        req = urllib.request.Request(f"http://{YLAVIRTA}/tokenize", data=data,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return len(json.loads(r.read().decode()).get("tokens", []))
    except urllib.error.HTTPError as e:
        runko = e.read().decode("utf-8", "replace")[:300]
        print(f"[kompaktointi] /tokenize {e.code}: {runko}",
              file=sys.stderr, flush=True)
        return None
    except Exception as e:
        print(f"[kompaktointi] /tokenize epäonnistui: {e}",
              file=sys.stderr, flush=True)
        return None


def _laske_tokenit(runko, malli):
    """Promptin tokenimäärä MAHDOLLISIMMAN TARKASTI. Ensisijaisesti /apply-template
    renderöi oikean promptin (chat-template + tools mukaan) ja se tokenoidaan ->
    tarkka. Jos endpointtia ei ole, arvioidaan pelkästä sisällöstä ja kerrotaan
    KERROIN:lla (muuten template + tool-boilerplate aliarvioituu ~1,5x, jolloin
    kompaktointi ei laukea ja vastaus katkeaa). Palauttaa tokenimäärän tai None."""
    global _tarkka_laskenta
    try:
        data = json.dumps({"messages": runko.get("messages", []),
                           "tools": runko.get("tools"), "model": malli}).encode()
        req = urllib.request.Request(f"http://{YLAVIRTA}/apply-template", data=data,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            prompt = json.loads(r.read().decode()).get("prompt")
        if isinstance(prompt, str):
            n = _tokenoi(prompt, malli)
            if n is not None:
                if _tarkka_laskenta is not True:
                    print("[kompaktointi] tokenlaskenta: /apply-template (tarkka)",
                          file=sys.stderr, flush=True)
                    _tarkka_laskenta = True
                return n
    except Exception:
        pass
    # Fallback: sisältö-estimaatti * KERROIN.
    if _tarkka_laskenta is not False:
        print(f"[kompaktointi] tokenlaskenta: sisältö-estimaatti * {KERROIN} "
              "(/apply-template ei käytettävissä)", file=sys.stderr, flush=True)
        _tarkka_laskenta = False
    raaka = _tokenoi(_kokoa_teksti(runko), malli)
    return None if raaka is None else int(raaka * KERROIN)


def _viestin_koko(msg):
    """Viestin sisällön merkkimäärä (str tai serialisoitu ei-str) — säästöarviota
    varten."""
    sis = msg.get("content")
    return len(sis) if isinstance(sis, str) else len(json.dumps(sis, ensure_ascii=False))


def _tiivistettava(msg):
    """Onko viesti tiivistettävissä: tekstivuoro (user/assistant), ei rakenteellinen
    (tool_calls), ei jo tiivistetty, ja tarpeeksi pitkä ollakseen sen arvoista."""
    if msg.get("role") not in ("user", "assistant") or msg.get("tool_calls"):
        return False
    sis = msg.get("content")
    return (isinstance(sis, str) and not sis.startswith(TIIVISTE_PREFIX)
            and len(sis) > TIIVISTE_MIN)


def _tiivista(teksti, malli):
    """Tiivistää tekstin ~3 lauseeseen llama.cpp:llä. Cachettu sisällön hashilla.
    Palauttaa TIIVISTE_PREFIX + tiivistelmä, tai None jos epäonnistui."""
    avain = hashlib.sha1(teksti.encode("utf-8")).hexdigest()
    if avain in _tiivistelmat:
        return _tiivistelmat[avain]
    pyynto = {
        "model": malli,
        "messages": [
            {"role": "system", "content": "Tiivistä käyttäjän viesti enintään "
             "kolmeen lauseeseen suomeksi. Säilytä olennaiset faktat, nimet ja "
             "päätökset. Vastaa vain tiivistelmällä, älä muuta."},
            {"role": "user", "content": teksti}],
        "stream": False,
        "max_tokens": 256,
        "chat_template_kwargs": {"enable_thinking": False},  # ei ajattelua tiivistykseen
    }
    try:
        data = json.dumps(pyynto).encode()
        req = urllib.request.Request(f"http://{YLAVIRTA}/v1/chat/completions",
                                     data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=AIKAKATKAISU) as r:
            d = json.loads(r.read().decode())
        tulos = TIIVISTE_PREFIX + d["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"[kompaktointi] tiivistys epäonnistui: {e}",
              file=sys.stderr, flush=True)
        tulos = None
    _tiivistelmat[avain] = tulos
    return tulos


class Kasittelija(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_):  # hiljaisempi loki; omat rivit sys.stderriin
        pass

    def _kerro(self, viesti):
        print(f"[kompaktointi] {viesti}", file=sys.stderr, flush=True)

    def _ylavirta_otsakkeet(self):
        h = {k: v for k, v in self.headers.items()
             if k.lower() not in OHITA_OTSAKKEET}
        # Pyydetään ylävirtaa sulkemaan yhteys vastauksen jälkeen, jotta
        # resp.read() saa EOF:n eikä proxy jää odottamaan keep-alive-yhteyttä.
        h["Connection"] = "close"
        return h

    def _laheta_ylavirtaan(self, data):
        """Yksi POST ylävirtaan. Palauttaa (status, resp_tai_body):
        200 -> avoin vastausolio (striimattavaksi); muu -> virhebody (bytes)."""
        url = f"http://{YLAVIRTA}{self.path}"
        pyynto = urllib.request.Request(url, data=data,
                                        headers=self._ylavirta_otsakkeet(),
                                        method="POST")
        try:
            resp = urllib.request.urlopen(pyynto, timeout=AIKAKATKAISU)
            return resp.status, resp
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def _striimaa(self, resp):
        """Välittää 200-vastauksen asiakkaalle muuttumattomana (myös SSE).
        Runko päätetään yhteyden sulkuun (Connection: close) — ei chunk-kehystystä
        eikä Content-Lengthiä, joten striimin pituutta ei tarvitse tietää etukäteen
        ja kehystysbugit poistuvat. Flush per pala, jotta tokenit näkyvät heti."""
        self.send_response_only(resp.status)
        for k, v in resp.headers.items():
            if k.lower() not in OHITA_OTSAKKEET:
                self.send_header(k, v)
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        # SSE-striimi: käsitellään rivi kerrallaan, jotta finish_reason "length"
        # -> "stop" -korjaus osuu vaikka rivi ylittäisi lukupalan rajan. Muut
        # (ei-striimaava JSON) korjataan koko bodystä.
        if "event-stream" in resp.headers.get("Content-Type", ""):
            # readline() palauttaa joka rivin heti kun \n saapuu -> aito
            # inkrementaalinen striimi. read(n) sen sijaan blokkaisi kunnes n
            # tavua tai yhteys sulkeutuu -> puskuroisi kaiken / jäätyisi jos
            # ylävirta pitää yhteyden auki [DONE]:n jälkeen.
            rivit = 0
            finish_nahty = False
            done_nahty = False
            alkup_length = False
            while True:
                try:
                    rivi = resp.readline()
                except (socket.timeout, TimeoutError):
                    self._kerro(f"SSE: idle-timeout {AIKAKATKAISU}s, "
                                "ylävirta ei lähetä eikä sulje -> päätetään")
                    break
                if not rivi:            # EOF
                    break
                rivit += 1
                if (b'"finish_reason"' in rivi
                        and b'"finish_reason":null' not in rivi
                        and b'"finish_reason": null' not in rivi):
                    finish_nahty = True
                if (b'"finish_reason":"length"' in rivi
                        or b'"finish_reason": "length"' in rivi):
                    alkup_length = True
                self.wfile.write(korjaa_length(rivi))
                self.wfile.flush()
                # SSE päättyy loogisesti [DONE]:hen — lopetetaan heti, ei jäädä
                # odottamaan yhteyden sulkua (muuten pi jäätyy).
                if b"[DONE]" in rivi:
                    done_nahty = True
                    break
            self._kerro(f"SSE loppui: {rivit} riviä, [DONE]={done_nahty}, "
                        f"finish_reason={finish_nahty}, alkup_length={alkup_length}")
            # Jos ylävirta katkaisi striimin ILMAN kunnollista lopetusta (esim.
            # konteksti täyttyi -> ei finish_reasonia eikä [DONE]:a), pi jäisi
            # odottamaan. Syntetisoidaan lopetus, jotta pi päättää vuoron.
            if not done_nahty:
                if not finish_nahty:
                    self.wfile.write(b'data: {"choices":[{"index":0,'
                                     b'"delta":{},"finish_reason":"stop"}]}\n\n')
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
        else:
            self.wfile.write(korjaa_length(resp.read()))
            self.wfile.flush()

    def _valita_virhe(self, status, body):
        self.send_response_only(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        self.wfile.write(body)

    def _lue_body(self):
        pituus = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(pituus) if pituus else b""

    def _sovita_konteksti(self, runko):
        """Hystereesi: kun prompti ylittää YLA_OSUUS ikkunasta, kompaktoi kunnes se
        on alle ALA_OSUUS. Näin ei ajeta joka pyynnöllä, ja alarajaan jää tilaa
        vastaukselle (estää 'prompti mahtuu mutta vastausbudjetti ~0 -> length').

        Rullaava tiivistys (jos TIIVISTA): tiivistetään vanhin tekstiviesti 3
        lauseeseen ennen pudotusta -> vanha konteksti säilyy tiivistelmänä täyden
        katoamisen sijaan. Rakenteelliset/lyhyet viestit pudotetaan kuten ennen."""
        konteksti = _hae_konteksti()
        ylaraja = int(konteksti * YLA_OSUUS)
        alaraja = int(konteksti * ALA_OSUUS)
        if alaraja <= 0:
            return
        malli = runko.get("model")
        n = _laske_tokenit(runko, malli)
        self._kerro(f"sovita: n_ctx={konteksti} yläraja={ylaraja} "
                    f"alaraja={alaraja} prompti≈{n} tok")
        if n is None or n <= ylaraja:
            return  # kynnys ei ylity (tai tokenointi ei käytettävissä)
        viestit = runko.get("messages", [])
        suhde = n / max(1, len(_kokoa_teksti(runko)))   # tok/merkki-arvio
        tiivistetty = pudotettu = 0
        # Säästö ARVIOIDAAN merkkimäärästä eikä kysytä /tokenize joka askeleella
        # (ennen ~40 round-trippiä/pyyntö). system ja viimeisin (nykyinen) viesti
        # säilyvät aina. 40% kohteessa on iso pelivara, joten arvion heitto ei
        # haittaa; tarkka luku lasketaan lopuksi lokiin.
        # Vaihe 1: tiivistä vanhat asiatekstit (säilytä ydin), vanhimmasta.
        if TIIVISTA:
            i = 0
            while n > alaraja and i < len(viestit) - 1:
                m = viestit[i]
                if _tiivistettava(m):
                    tiiv = _tiivista(m["content"], malli)
                    if tiiv:
                        n -= int(max(0, _viestin_koko(m) - len(tiiv)) * suhde)
                        m["content"] = tiiv
                        tiivistetty += 1
                i += 1
        # Vaihe 2: jos yhä yli, pudota vanhimmasta (myös tiivistelmät) kunnes alle.
        while n > alaraja:
            idx = next((j for j, m in enumerate(viestit[:-1])
                        if m.get("role") != "system"), None)
            if idx is None:
                break                          # vain system + viimeisin jäljellä
            n -= int(_viestin_koko(viestit[idx]) * suhde)
            del viestit[idx]
            pudotettu += 1
        if tiivistetty or pudotettu:
            todellinen = _laske_tokenit(runko, malli)   # tarkka luku lokiin (1 kutsu)
            self._kerro(f"sovitus: tiivistetty {tiivistetty}, pudotettu {pudotettu} "
                        f"-> ~{todellinen} tok (yläraja {ylaraja} ylittyi -> kohde {alaraja})")

    def _lapivienti(self, body):
        """Ei-chat-POST-pyynnöt: välitä sellaisenaan (POST), ei katkaisua."""
        status, tulos = self._laheta_ylavirtaan(body)
        if status == 200:
            self._striimaa(tulos)
        else:
            self._valita_virhe(status, tulos)

    def _get_ylavirtaan(self):
        url = f"http://{YLAVIRTA}{self.path}"
        pyynto = urllib.request.Request(url, headers=self._ylavirta_otsakkeet(),
                                        method="GET")
        try:
            resp = urllib.request.urlopen(pyynto, timeout=AIKAKATKAISU)
            return resp.status, resp
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def do_GET(self):
        self._kerro(f"GET {self.path}")
        try:
            status, tulos = self._get_ylavirtaan()
            self._kerro(f"GET {self.path} -> {status}")
            self._striimaa(tulos) if status == 200 else self._valita_virhe(status, tulos)
        except Exception as e:
            self._kerro(f"GET-virhe: {e}")
            self._valita_virhe(502, json.dumps({"error": str(e)}).encode())

    def do_POST(self):
        body = self._lue_body()
        self._kerro(f"POST {self.path} ({len(body)} tavua)")
        # Vain chat-completions katkaistaan; muut menevät läpi.
        if not self.path.endswith("/chat/completions"):
            try:
                self._lapivienti(body)
            except Exception as e:
                self._kerro(f"läpivienti-virhe: {e}")
                self._valita_virhe(502, json.dumps({"error": str(e)}).encode())
            return
        try:
            runko = json.loads(body)
        except Exception:
            self._lapivienti(body)  # ei JSON — päästä ylävirran hoidettavaksi
            return

        self._sovita_konteksti(runko)  # headroom-leikkaus ennen lähetystä
        pudotettu = 0
        while True:
            data = json.dumps(runko).encode("utf-8")
            try:
                status, tulos = self._laheta_ylavirtaan(data)
            except Exception as e:
                self._kerro(f"ylävirtavirhe: {e}")
                self._valita_virhe(502, json.dumps({"error": str(e)}).encode())
                return
            if status == 200:
                self._kerro(f"-> 200, striimataan"
                            + (f" (pudotettu {pudotettu} palaa)" if pudotettu else ""))
                self._striimaa(tulos)
                return
            # Kontekstin ylitys -> kutista ja yritä uudelleen.
            if status == 400 and b"exceed_context_size" in tulos and pudota_vanhin(runko):
                pudotettu += 1
                continue
            # Muu virhe tai ei enää kutistettavaa -> välitä virhe asiakkaalle.
            self._kerro(f"-> {status} (välitetään virhe)")
            self._valita_virhe(status, tulos)
            return


def _itsetesti():
    # ponytail: puhdas katkaisulogiikka ilman verkkoa — pettää jos rakenne rikkoutuu.
    r = {"messages": [
        {"role": "system", "content": "olet apuri"},
        {"role": "user", "content": "eka"},
        {"role": "assistant", "content": "vast1"},
        {"role": "user", "content": "toka"}]}
    assert pudota_vanhin(r) is True
    roolit = [v["role"] for v in r["messages"]]
    assert roolit[0] == "system", roolit          # system säilyy
    assert "eka" not in json.dumps(r["messages"])  # vanhin ei-system pudonnut

    # Kutista loppuun asti: jäljelle jää system + 1, sitten puolitus.
    yksi = {"messages": [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "abcdefgh"}]}
    assert pudota_vanhin(yksi) is True
    assert yksi["messages"][1]["content"] == "efgh"  # loppupuolisko säilyy

    # Multimodaali: tekstiosa puolittuu.
    mm = {"messages": [{"role": "user", "content": [
        {"type": "text", "text": "12345678"},
        {"type": "image_url", "image_url": {"url": "data:..."}}]}]}
    assert pudota_vanhin(mm) is True
    assert mm["messages"][0]["content"][0]["text"] == "5678"

    # finish_reason length -> stop (molemmat välilyöntimuodot), muu säilyy.
    assert korjaa_length(b'{"finish_reason":"length"}') == b'{"finish_reason":"stop"}'
    assert korjaa_length(b'{"finish_reason": "length"}') == b'{"finish_reason": "stop"}'
    assert korjaa_length(b'{"finish_reason":"stop"}') == b'{"finish_reason":"stop"}'

    # Tiivistettävyys: vain riittävän pitkä user/assistant-teksti; system,
    # rakenteellinen (tool_calls), liian lyhyt ja jo-tiivistetty ohitetaan.
    assert _tiivistettava({"role": "user", "content": "x" * 300}) is True
    assert _tiivistettava({"role": "system", "content": "x" * 300}) is False
    assert _tiivistettava({"role": "assistant", "content": "x" * 300,
                           "tool_calls": [{}]}) is False
    assert _tiivistettava({"role": "user", "content": "lyhyt"}) is False
    assert _tiivistettava({"role": "user",
                           "content": TIIVISTE_PREFIX + "x" * 300}) is False

    # Ei mitään kutistettavaa -> False.
    tyhja = {"messages": [{"role": "system", "content": "s"},
                          {"role": "user", "content": "x"}]}
    pudota_vanhin(tyhja)          # puolittaa "x"? len<=1 -> False
    assert pudota_vanhin(tyhja) is False
    print("OK")


if __name__ == "__main__":
    if "--test" in sys.argv:
        _itsetesti()
        sys.exit(0)
    print(f"[kompaktointi] kuuntelen :{PORTTI} -> {YLAVIRTA}", file=sys.stderr)
    ThreadingHTTPServer(("0.0.0.0", PORTTI), Kasittelija).serve_forever()
