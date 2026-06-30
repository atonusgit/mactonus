# Telegram-silta

Ajaa **pi-agenttia** headless Telegramin yli: käyttäjän viestit menevät pi:lle, ja viesteissä olevat linkit käsitellään **deterministisesti ennen pi:tä**. pi saa tulokseksi tiedostopolun (ei koko sisältöä → ei kontekstin räjäytystä).

```mermaid
flowchart TB
    Msg([Telegram-viesti]) --> T{tekstiä?}
    T -->|ei liite| NO["vastaa: liitteitä ei lueta"]
    T -->|kyllä| B["telegram_silta.py<br/>esikasittele"]
    B --> Y{YouTube-linkki?}
    Y -->|kyllä| YT["lataa_transkriptio.sh"]
    Y -->|ei| P{.pdf-linkki?}
    P -->|kyllä| PD["tallenna_pdf.py"]
    P -->|ei| W{muu http-linkki?}
    W -->|kyllä| WS["tallenna_verkkosivu.py"]
    W -->|ei| PI
    YT --> PI["pi-agentti<br/>(saa tiedostopolun)"]
    PD --> PI
    WS --> PI
    PI -->|vastaus| Msg
```

## Toiminta

- Vain `TELEGRAM_SALLITUT_CHATIT`-listan chatit pääsevät läpi (pi voi ajaa bashia ja kirjoittaa vaultiin).
- Linkkien deterministinen käsittely tapahtuu ennen pi:tä → johdonmukainen lopputulos, ei agentin improvisointia. Reititys: YouTube → litterointi, `.pdf`-URL → PDF-tiivistys, muu http(s) → verkkosivutiivistys.
- **Liitetiedostoja ei vielä lueta** — teksitön viesti (esim. PDF tiedostona) saa vastauksen siitä, ei hiljaista ohitusta. PDF kannattaa jakaa **linkkinä**.
- pi:tä voi ajaa myös interaktiivisesti ilman siltaa: `docker exec -it mactonus pi`.

## Kytkimet (`.env`)

`TELEGRAM_BOT_TOKEN` (tyhjä → silta ei käynnisty), `TELEGRAM_SALLITUT_CHATIT`, `YOUTUBE_LATAUS`, `VERKKOSIVU_TALLENNUS`.
