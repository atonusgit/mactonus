#!/usr/bin/env python3
# n8n_mcp.py — Ohut MCP-client (streamable HTTP) pi:n skilliä varten.
#
# Puhuu n8n:n "MCP Server Trigger" -nodelle JSON-RPC 2.0:lla HTTP:n yli ilman
# ulkoisia riippuvuuksia (vain stdlib -> toimii python:3.12-slim:ssä sellaisenaan).
# pi:llä ei ole sisäänrakennettua MCP-clientiä, joten tämä skripti hoitaa
# protokollan ja tarjoaa agentille kaksi komentoa: työkalujen listaus ja ajo.
#
# Käyttö:
#   python3 n8n_mcp.py lista
#   python3 n8n_mcp.py aja <tyokalun_nimi> '<json-argumentit>'
#
# Ympäristö (.env -> docker-compose env_file):
#   N8N_MCP_URL    pakollinen — MCP Server Trigger -noden streamable HTTP -endpoint
#   N8N_MCP_TOKEN  valinnainen — bearer-token, jos triggerissä on autentikointi

import json, os, sys, urllib.request, urllib.error

PROTOKOLLA = "2025-06-18"  # MCP-protokollaversio


def _post(url, token, sessio, viesti):
    """Lähettää yhden JSON-RPC-viestin. Palauttaa (sessio, content-type, runko)."""
    data = json.dumps(viesti).encode("utf-8")
    pyynto = urllib.request.Request(url, data=data, method="POST")
    pyynto.add_header("Content-Type", "application/json")
    pyynto.add_header("Accept", "application/json, text/event-stream")
    if token:
        pyynto.add_header("Authorization", f"Bearer {token}")
    if sessio:
        pyynto.add_header("Mcp-Session-Id", sessio)
    try:
        with urllib.request.urlopen(pyynto, timeout=60) as vastaus:
            uusi_sessio = vastaus.headers.get("Mcp-Session-Id") or sessio
            tyyppi = vastaus.headers.get("Content-Type", "")
            runko = vastaus.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP-virhe {e.code}: {e.read().decode('utf-8', 'replace')[:500]}")
    except urllib.error.URLError as e:
        sys.exit(f"Yhteysvirhe ({url}): {e.reason}")
    return uusi_sessio, tyyppi, runko


def _poimi_tulos(tyyppi, runko):
    """Jäsentää vastauksen: tukee sekä application/json- että SSE-runkoa."""
    # Notifikaatioihin (ei id:tä) palvelin vastaa tyhjällä rungolla / 202.
    if not runko.strip():
        return None
    if "text/event-stream" in tyyppi:
        # SSE: kerää ensimmäisen tapahtuman data:-rivit ja jäsennä ne.
        palat = []
        for rivi in runko.splitlines():
            if rivi.startswith("data:"):
                palat.append(rivi[5:].strip())
            elif not rivi.strip() and palat:
                break
        runko = "\n".join(palat)
        if not runko:
            return None
    return json.loads(runko)


def _kutsu(url, token, sessio, metodi, params, idnro):
    """JSON-RPC-pyyntö (odottaa tuloksen). Palauttaa (sessio, result)."""
    viesti = {"jsonrpc": "2.0", "id": idnro, "method": metodi, "params": params}
    sessio, tyyppi, runko = _post(url, token, sessio, viesti)
    tulos = _poimi_tulos(tyyppi, runko)
    if tulos and "error" in tulos:
        sys.exit(f"MCP-virhe metodissa {metodi}: "
                 f"{json.dumps(tulos['error'], ensure_ascii=False)}")
    return sessio, (tulos or {}).get("result")


def _ilmoita(url, token, sessio, metodi):
    """JSON-RPC-notifikaatio (ei id:tä, ei odotettua tulosta)."""
    _post(url, token, sessio, {"jsonrpc": "2.0", "method": metodi})


def yhdista(url, token):
    """MCP-kättely: initialize -> initialized. Palauttaa sessio-id:n."""
    sessio, _ = _kutsu(url, token, None, "initialize", {
        "protocolVersion": PROTOKOLLA,
        "capabilities": {},
        "clientInfo": {"name": "pi-tilauspalvelutallennus", "version": "1.0"},
    }, 1)
    _ilmoita(url, token, sessio, "notifications/initialized")
    return sessio


def komento_lista(url, token, sessio):
    _, tulos = _kutsu(url, token, sessio, "tools/list", {}, 2)
    tyokalut = (tulos or {}).get("tools", [])
    if not tyokalut:
        print("(ei työkaluja — tarkista että MCP Server Trigger -node on aktiivinen)")
        return
    for t in tyokalut:
        print(f"- {t.get('name')}: {(t.get('description') or '').strip()}")
        skeema = t.get("inputSchema") or {}
        if skeema.get("properties"):
            print(f"    argumentit: "
                  f"{json.dumps(skeema['properties'], ensure_ascii=False)}")


def komento_aja(url, token, sessio, nimi, argumentit_raaka):
    argumentit = json.loads(argumentit_raaka) if argumentit_raaka.strip() else {}
    _, tulos = _kutsu(url, token, sessio, "tools/call",
                      {"name": nimi, "arguments": argumentit}, 3)
    for osa in (tulos or {}).get("content", []):
        if osa.get("type") == "text":
            print(osa.get("text", ""))
        else:
            print(json.dumps(osa, ensure_ascii=False))
    if (tulos or {}).get("isError"):
        sys.exit(1)


def main():
    url = os.environ.get("N8N_MCP_URL", "").strip()
    token = os.environ.get("N8N_MCP_TOKEN", "").strip() or None
    if not url:
        sys.exit("N8N_MCP_URL puuttuu ympäristöstä (.env).")
    if len(sys.argv) < 2:
        sys.exit("Käyttö: n8n_mcp.py lista | aja <työkalu> '<json-argumentit>'")

    komento = sys.argv[1]
    sessio = yhdista(url, token)

    if komento == "lista":
        komento_lista(url, token, sessio)
    elif komento == "aja":
        if len(sys.argv) < 3:
            sys.exit("Käyttö: n8n_mcp.py aja <työkalu> '<json-argumentit>'")
        nimi = sys.argv[2]
        argumentit_raaka = sys.argv[3] if len(sys.argv) > 3 else ""
        komento_aja(url, token, sessio, nimi, argumentit_raaka)
    else:
        sys.exit(f"Tuntematon komento: {komento}")


if __name__ == "__main__":
    main()
