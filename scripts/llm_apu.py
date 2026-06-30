"""Jaettu LLM-kutsu mactonus-skripteille.

Käyttää OpenAI-yhteensopivaa /v1/chat/completions -rajapintaa, jota llama.cpp ja
useimmat muut paikalliset backendit puhuvat. Backendin vaihto on yhden rivin
muutos config.py:ssä (LLM_URL) — skripteihin ei tarvitse koskea.
"""
import base64, json, os, urllib.request
from config import LLM_URL, LLM_AIKAKATKAISU, MALLI_TEKSTIT


def _rakenna_runko(kehote, *, kuva_uri=None, systeemi=None,
                   malli=MALLI_TEKSTIT, json_muoto=False):
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
    return runko


def kysy_llm(kehote, *, kuva=None, systeemi=None, malli=None, url=None,
             aikakatkaisu=None, json_muoto=False):
    """Lähettää kehotteen LLM:lle ja palauttaa vastaustekstin (str).

    kuva        polku kuvatiedostoon -> lähetetään multimodaalisena (data-URI).
    systeemi    valinnainen system-viesti.
    json_muoto  pakota validi JSON-vastaus.
    url         ohita LLM_URL (esim. hostilta ajettaessa localhost).
    Nostaa poikkeuksen HTTP-/verkkovirheessä — kutsuja päättää käsittelyn.
    """
    kuva_uri = None
    if kuva:
        with open(kuva, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        # ponytail: mime tiedostopäätteestä; jpg->jpeg, muut sellaisenaan
        paate = os.path.splitext(kuva)[1].lower().lstrip(".") or "jpeg"
        mime = "jpeg" if paate in ("jpg", "jpeg") else paate
        kuva_uri = f"data:image/{mime};base64,{b64}"

    runko = _rakenna_runko(kehote, kuva_uri=kuva_uri, systeemi=systeemi,
                           malli=malli or MALLI_TEKSTIT, json_muoto=json_muoto)
    data = json.dumps(runko).encode("utf-8")
    pyynto = urllib.request.Request(url or LLM_URL, data=data,
                                    headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(pyynto, timeout=aikakatkaisu or LLM_AIKAKATKAISU) as vastaus:
        data = json.loads(vastaus.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]


if __name__ == "__main__":
    # ponytail: rungon rakenne ilman verkkoa — pettää jos viestiformaatti rikkoutuu.
    r = _rakenna_runko("hei", systeemi="olet apuri", json_muoto=True)
    assert r["messages"][0]["role"] == "system"
    assert r["messages"][1]["content"] == "hei"
    assert r["response_format"] == {"type": "json_object"}
    r2 = _rakenna_runko("mitä tässä", kuva_uri="data:image/jpeg;base64,AAAA")
    assert r2["messages"][-1]["content"][1]["image_url"]["url"].startswith("data:image/jpeg")
    print("OK")
