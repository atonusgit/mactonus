"""Jaettu LLM-kutsu mactonus-skripteille.

Käyttää OpenAI-yhteensopivaa /v1/chat/completions -rajapintaa, jota llama.cpp ja
useimmat muut paikalliset backendit puhuvat. Backendin vaihto on yhden rivin
muutos config.py:ssä (LLM_URL) — skripteihin ei tarvitse koskea.
"""
import base64, io, json, urllib.request, urllib.error
from config import LLM_URL, LLM_AIKAKATKAISU, MALLI_TEKSTIT, KUVA_MAKS_REUNA


def _pienenna_kuva(lahde, maks_reuna=KUVA_MAKS_REUNA):
    """Pienentää kuvan max-reunaan, palauttaa JPEG-base64:n. Säilyttää kuvasuhteen,
    ei suurenna. PIL tuodaan funktiossa, jotta moduuli toimii ilman sitä (esim. testit)."""
    from PIL import Image
    kuva = Image.open(lahde).convert("RGB")
    kuva.thumbnail((maks_reuna, maks_reuna))  # vain pienentää, säilyttää suhteen
    puskuri = io.BytesIO()
    kuva.save(puskuri, format="JPEG", quality=85)
    return base64.b64encode(puskuri.getvalue()).decode()


def _rakenna_runko(kehote, *, kuva_uri=None, systeemi=None,
                   malli=MALLI_TEKSTIT, json_muoto=False, ajattele=False):
    """Rakentaa /v1/chat/completions -pyyntörungon. Pidetty erillään verkosta,
    jotta rakenne on testattavissa (ks. __main__)."""
    viestit = []
    if systeemi:
        viestit.append({"role": "system", "content": systeemi})
    if kuva_uri:
        viestit.append({"role": "user", "content": [
            {"type": "text", "text": kehote},
            {"type": "image_url", "image_url": {"url": kuva_uri}}]})
    else:
        viestit.append({"role": "user", "content": kehote})
    runko = {"model": malli, "messages": viestit, "stream": False}
    if json_muoto:
        runko["response_format"] = {"type": "json_object"}
    # Ajattelu (reasoning) pois oletuksena: kaikki cron-kutsut ovat mekaanisia
    # poiminta-/siistimis-/tiivistystehtäviä, jotka eivät hyödy ketjuajattelusta
    # ja joita se vain hidastaa (+ voi sotkea json_muodon). Lähetetään aina
    # eksplisiittisesti, jottei tulos riipu serverin oletuksesta. chat_template_kwargs
    # on paikallisten template-backendien (llama.cpp/vLLM) tapa ohjata thinkingiä.
    runko["chat_template_kwargs"] = {"enable_thinking": bool(ajattele)}
    return runko


def kysy_llm(kehote, *, kuva=None, systeemi=None, malli=None, url=None,
             aikakatkaisu=None, json_muoto=False, ajattele=False):
    """Lähettää kehotteen LLM:lle ja palauttaa vastaustekstin (str).

    kuva        polku kuvatiedostoon -> lähetetään multimodaalisena (data-URI).
    systeemi    valinnainen system-viesti.
    json_muoto  pakota validi JSON-vastaus.
    ajattele    salli mallin ketjuajattelu (thinking). Oletus False — mekaaniset
                tehtävät eivät sitä tarvitse ja se vain hidastaa.
    url         ohita LLM_URL (esim. hostilta ajettaessa localhost).
    Nostaa poikkeuksen HTTP-/verkkovirheessä — kutsuja päättää käsittelyn.
    """
    kuva_uri = None
    if kuva:
        # Pienennetään aina JPEG:ksi: välttää 413:n ja nopeuttaa visiota.
        kuva_uri = f"data:image/jpeg;base64,{_pienenna_kuva(kuva)}"

    runko = _rakenna_runko(kehote, kuva_uri=kuva_uri, systeemi=systeemi,
                           malli=malli or MALLI_TEKSTIT, json_muoto=json_muoto,
                           ajattele=ajattele)
    data = json.dumps(runko).encode("utf-8")
    pyynto = urllib.request.Request(url or LLM_URL, data=data,
                                    headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(pyynto, timeout=aikakatkaisu or LLM_AIKAKATKAISU) as vastaus:
            data = json.loads(vastaus.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        # Nostetaan serverin oma virheviesti esiin (urllib piilottaa sen muuten).
        runko_virhe = e.read().decode("utf-8", "replace")[:500]
        raise RuntimeError(f"LLM {e.code}: {runko_virhe}") from e
    return data["choices"][0]["message"]["content"]


if __name__ == "__main__":
    # ponytail: rungon rakenne ilman verkkoa — pettää jos viestiformaatti rikkoutuu.
    r = _rakenna_runko("hei", systeemi="olet apuri", json_muoto=True)
    assert r["messages"][0]["role"] == "system"
    assert r["messages"][1]["content"] == "hei"
    assert r["response_format"] == {"type": "json_object"}
    assert r["chat_template_kwargs"] == {"enable_thinking": False}  # ajattelu pois oletuksena
    assert _rakenna_runko("hei", ajattele=True)["chat_template_kwargs"] == {"enable_thinking": True}
    r2 = _rakenna_runko("mitä tässä", kuva_uri="data:image/jpeg;base64,AAAA")
    assert r2["messages"][-1]["content"][1]["image_url"]["url"].startswith("data:image/jpeg")
    try:
        from PIL import Image
        puskuri = io.BytesIO()
        Image.new("RGB", (4000, 2000)).save(puskuri, "PNG")
        puskuri.seek(0)
        ulos = Image.open(io.BytesIO(base64.b64decode(_pienenna_kuva(puskuri, maks_reuna=512))))
        assert max(ulos.size) <= 512, ulos.size  # pienennetty oikein, suhde säilyy
        print("OK (kuva-resize mukana)")
    except ImportError:
        print("OK (PIL ei asennettu — resize-testi ohitettu)")
