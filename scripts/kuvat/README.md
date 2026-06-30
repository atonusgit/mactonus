# Kuva-analyysi — kuvailutulkkaus + jalostus

Cron-pohjainen työnkulku kontissa: löytää vaultin `**/Liitteet/`-kuvat, tuottaa kuvauksen (Ollama `MALLI_KUVAT`), linkittää viereisiin muistiinpanoihin, ja jalostaa erikseen merkityt kuvatekstit.

```mermaid
sequenceDiagram
    autonumber
    box rgb(255, 243, 224) Kontti
        participant Cron as cron
        participant AI as kuvat/analysoi_kuvat.sh
        participant Enc as kuvat/enkoodaa_kuva.py
        participant Ref as kuvat/jalosta_kuvatekstit.py
    end
    box rgb(243, 229, 245) Vault
        participant V as /vault
    end
    box rgb(232, 245, 233) Host-palvelin
        participant Ol as Ollama
    end

    Note over Cron,V: Vaihe 1 — kuvailutulkkaus, joka 15 min
    Cron->>AI: */15 min
    AI->>V: hae **/Liitteet/*.{png,jpg} ilman _teksti.md
    loop kuvat (max 20/ajo, flock estää päällekkäiset ajot)
        AI->>Enc: timeout 120 python3 enkoodaa_kuva.py
        Enc->>V: lue kuva (base64) + Kehotteet/Analysoi kuva.md
        Enc->>Ol: POST /api/generate (MALLI_KUVAT)
        Ol-->>Enc: kuvaus
        Enc->>V: kirjoita _teksti.md
        AI->>V: lisää [[linkki]] viereisiin .md-tiedostoihin
    end

    Note over Cron,V: Vaihe 2 — jalostus, joka 5 min
    Cron->>Ref: */5 min (flock)
    Ref->>V: hae *_teksti.md tägillä #siisti-kuvailutulkkaus
    loop merkityt (max 4/ajo)
        Ref->>Ol: POST (MALLI_TEKSTIT)
        Ol-->>Ref: jalostettu kuvaus + avainsanat
        Ref->>V: korvaa sisältö, poista tägi
    end
```

## Skriptit

- `analysoi_kuvat.sh` — cron-wrapper (flock), max 20 kuvaa/ajo
- `enkoodaa_kuva.py` — kuva (base64) + kehote → `MALLI_KUVAT` → `*_teksti.md`
- `jalosta_kuvatekstit.py` — `#siisti-kuvailutulkkaus`-merkityt → `MALLI_TEKSTIT` → siistitty kuvaus + avainsanat

Kuva-analyysin kehote: `<vault>/mactonus/Kehotteet/Analysoi kuva.md` (valinnainen, fallback inline-defaulttiin).
