# EU digital sovereignty — daily

Cron-työnkulku: hakee EU:n digitaaliseen suvereniteettiin ja paikallisiin tekoälymalleihin liittyviä uutisia (Staan-verkkohaku), valitsee relevanteimmat, lukee ja tiivistää sisällön, tulkitsee Sitran näkökulman, lähettää Telegram-digestin ja arkistoi vaultiin.

```mermaid
sequenceDiagram
    autonumber
    participant Cron as cron
    participant D as daily.py
    participant St as Staan API
    participant Ol as llama.cpp
    participant Mi as Mistral
    participant Tg as Telegram
    participant V as Vault (Clippings/Staan)

    Cron->>D: päivittäin
    D->>St: verkkohaku (hakutermit)
    D->>Ol: valitse relevanteimmat (MALLI_TEKSTIT)
    loop valitut uutiset
        D->>St: hae sivun sisältö (verkko_apu, robots)
        D->>Mi: tiivistä sisältö
        D->>Ol: Sitra-tulkinta (MALLI_TEKSTIT)
        D->>Tg: lähetä digesti
        D->>V: arkistoi (dedup source-URL)
    end
```

## Mallien jako

- **Sivun tiivistys → Mistral** (julkista dataa, nopea pilvi).
- **Uutisten valinta + Sitra-tulkinta → paikallinen llama.cpp** (`MALLI_TEKSTIT`) — Sitra-spesifistä päättelyä, ei ulkoisteta.
- **Kaavinta** jaettu verkkosivu-tiivistyksen kanssa (`verkko_apu.py`).

Vaatii `STAAN_API_KEY`:n ja (tiivistykseen) `MISTRAL_API_KEY`:n. Arkisto toimii dedup-lähteenä: jo lähetettyjä URL:eja ei valita uudestaan.
