# Kommentointi — VoxCPM2-pohjainen ääniagentti

Reaaliaikainen ääniagentti: seuraa käynnissä olevaa nauhoitusistuntoa, tuottaa puhutun kommentin (Ollama `MALLI_KOMMENTOIJA`) ja syntetisoi sen ääneksi (VoxCPM2 `:8179`).

```mermaid
sequenceDiagram
    autonumber
    actor U as Käyttäjä
    box rgb(255, 243, 224) Kontti
        participant Co as puhe/commenter.py
    end
    box rgb(243, 229, 245) Vault
        participant V as Nauhoitukset/tmp_chunks/SESSIO/
    end
    box rgb(232, 245, 233) Host-palvelimet
        participant Ol as Ollama
        participant Vx as voxcpm2_server :8179
    end
    box rgb(245, 245, 245) Laite
        participant S as Kaiuttimet
    end

    U->>Co: comm (docker exec)
    Co->>V: lue Kehotteet/Kommentoija.md
    loop poll 3 s välein
        Co->>V: tarkkaile aktiivisen SESSIO:n uusia _NNN.txt:iä
        alt uusia ≥ kynnys (1)
            Co->>Co: siisti raakalitterointi (string-ops)
            Co->>Ol: POST (MALLI_KOMMENTOIJA, kehote + litterointi)
            Ol-->>Co: kommentti
            Co->>Vx: POST {text, ref, play=true}
            Vx->>S: synthesize + soita
            Vx-->>Co: ok
        end
    end
```

## Skriptit

- `commenter.py` — kuuntelee aktiivista istuntoa ja kommentoi (`comm` = docker exec)
- `say.py` — yksinkertainen TTS-asiakas debuggaukseen (`host.docker.internal:8179`)

Vaatii kehotteen `<vault>/mactonus/Kehotteet/Kommentoija.md` ja käynnissä olevan VoxCPM2-palvelimen ([`paikallinen-puheassistentti`](https://github.com/atonusgit/paikallinen-puheassistentti)).
