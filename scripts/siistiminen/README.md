# Tekstien siistiminen — muistiinpanot + transkriptit

Kaksi siistimistyönkulkua: cron-pohjainen muistiinpanojen siistiminen ja manuaalinen transkriptien jalostus valitulla dokumenttimuoto-kehotteella.

```mermaid
sequenceDiagram
    autonumber
    actor U as Käyttäjä
    box rgb(255, 243, 224) Kontti
        participant Cron as cron
        participant CO as siistiminen/siisti_muistiinpanot.py
        participant CT as siistiminen/siisti_transkriptit.py
    end
    box rgb(243, 229, 245) Vault
        participant V as /vault
    end
    box rgb(232, 245, 233) Host-palvelin
        participant Ol as Ollama
    end

    Note over Cron,CO: Cron-pohjainen — muistiinpanot
    Cron->>CO: * * * * * (joka minuutti)
    CO->>V: hae /vault/**/*.md (paitsi /vault/mactonus/), *[siisti]*-merkki
    loop merkityt (max 4/ajo)
        CO->>Ol: POST (MALLI_TEKSTIT, inline-kehote)
        Ol-->>CO: siistitty teksti
        CO->>V: korvaa sisältö, lisää *[Siistitty: pvm]*
    end

    Note over U,CT: Manuaalinen — transkriptit
    U->>CT: docker exec ... siisti_transkriptit.py [prompt]
    CT->>V: lue Dokumenttimuoto-kehotteet/<prompt>.md
    CT->>V: hae Nauhoitukset/*.md, *[siisti]*-merkki
    loop merkityt (max 4)
        CT->>Ol: POST (MALLI_TEKSTIT, prompt + sisältö)
        Ol-->>CT: jalostettu teksti
        CT->>V: kirjoita SESSIO_<prompt>.md
    end
```

## Skriptit

- `siisti_muistiinpanot.py` — `*[siisti]*`-merkityt `/vault/**/*.md` (cron 1 min); kehote inline-koodissa
- `siisti_transkriptit.py [prompt]` — `Nauhoitukset/*.md` + valittu `Dokumenttimuoto-kehotteet/<prompt>.md` (manuaalinen)
