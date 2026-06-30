# Mactonus

**Mactonus** on tekoälyagentin paikallinen **kyvykkyyskerros**: keho ja työkalut, jotka pyörivät omalla raudallasi. Agentin äly (pi) on erillinen, **vaihdettava** komponentti — tämä repo on itse kyvyt ja niiden orkestrointi: litterointi, kuva-analyysi, sisällön tiivistäminen, verkkohaku, etäkomennot, kotiautomaatio ja Obsidian-vaultin ylläpito. Osa kyvyistä on agentin skillien kutsuttavissa, osa pyörii itsenäisesti ajastettuna ilman agenttia.

Yksityinen data käsitellään paikallisilla malleilla — ei mene ulos. Julkisen datan tiivistys voi käyttää nopeaa **Mistral-pilvimallia** (valinnainen, vaatii `MISTRAL_API_KEY`:n). Paikallinen LLM-, litterointi- ja TTS-inferenssi pyörii hostilla Metal-kiihdytyksellä.

## Yleisarkkitehtuuri

```mermaid
flowchart TB
    User([Käyttäjä])
    subgraph Pilvi["Pilvi — vain julkinen data"]
        Mistral["Mistral API<br/>tiivistys"]
        Staan["Staan API<br/>verkkohaku"]
    end
    subgraph Host["macOS-host (Metal-GPU)"]
        Ollama["Ollama :11434"]
        Whisper["whisper.cpp :8178"]
        Vox["voxcpm2 :8179"]
    end
    subgraph Kontti["Docker-kontti: mactonus"]
        Cron["cron<br/>itsenäiset työnkulut"]
        Pi["pi-agentti<br/>(Telegram-silta / CLI)"]
        Scripts["scripts/ — kyvyt"]
    end
    Vault[("Obsidian-vault<br/>/vault")]
    PiRepo[[".pi — agentin äly<br/>skillit · muisti · malli"]]

    User -->|Telegram / CLI| Pi
    Pi -->|skill → ajaa| Scripts
    Cron -->|ajastettu| Scripts
    Pi -.lukee.-> PiRepo
    Scripts -->|paikallinen LLM / STT / TTS| Ollama & Whisper & Vox
    Scripts -->|julkisen datan tiivistys| Mistral
    Scripts -->|verkkohaku| Staan
    Scripts <-->|luku / kirjoitus| Vault

    classDef pilvi fill:#fde0dc,stroke:#c62828,color:#000
    classDef palvelin fill:#e8f5e9,stroke:#2e7d32,color:#000
    classDef kontti fill:#fff3e0,stroke:#ef6c00,color:#000
    classDef vaultcls fill:#f3e5f5,stroke:#7b1fa2,color:#000
    classDef agent fill:#e3f2fd,stroke:#1976d2,color:#000
    class Mistral,Staan pilvi
    class Ollama,Whisper,Vox palvelin
    class Cron,Pi,Scripts kontti
    class Vault vaultcls
    class PiRepo agent
```

**Keskeinen periaate:** Ollama, whisper.cpp ja VoxCPM2 pyörivät **hostilla**, eivät kontissa, koska Docker Desktop ei läpäise Metal-GPU:ta. Kontissa pyörii vain orkestrointi (cron + Python + pi). Konttisisäiset skriptit kutsuvat hostin palveluja `host.docker.internal`-osoitteen kautta.

## Agentti, skillit ja skriptit

Osaa työnkuluista ohjaa **pi-agentti** (pi-coding-agent), joka pyörii kontissa. Telegram-silta (`telegram/telegram_bridge.py`) ajaa pi:tä headless: käyttäjän viestit menevät pi:lle, ja viesteissä olevat linkit käsitellään deterministisesti jo ennen pi:tä (YouTube-litterointi, verkkosivutiivistys). pi:tä voi ajaa myös interaktiivisesti: `docker exec -it mactonus pi`.

Agentti ja koodi on eriytetty **kahteen git-repoon**:

- **`mactonus/` (tämä repo — koodi):** kaikki suoritettava kyky asuu `scripts/`:ssä. Sama skripti palvelee niin cronia kuin agentin skilliäkin. Jaetut moduulit (`config.py`, `mistral_apu.py`, `verkko_apu.py`, `tiedosto_apu.py`) ovat `scripts/`-juuressa.
- **`.pi/` (erillinen repo — agentti):** agentin skillit, muisti, persoona ja malliasetukset.

**Periaate — "skillit kuvaavat, skriptit tekevät":** skill on ohut `SKILL.md`-osoitin, joka kertoo agentille *milloin* ja *minkä* `scripts/`-skriptin ajaa; suoritettava logiikka asuu aina `scripts/`:ssä. Näin sama kyky toimii agentista riippumatta (cron, käsin tai vaikka toinen agentti).

## Työnkulut

Kunkin työnkulun **tarkempi toiminta ja kuvaaja** on sen oman kansion READMEssä (linkit alla).

| Työnkulku | Laukaisin | Skripti(t) | Malli | Syöte → Tuloste |
|---|---|---|---|---|
| [Nauhoitus + litterointi](scripts/litterointi/) | manuaalinen (host) | `litterointi/record_and_transcribe.sh` + `transcribe_session.sh` | whisper large-v3-turbo | mikki → `.md` Obsidianiin |
| [Yksittäinen wav](scripts/litterointi/) | manuaalinen (host) | `litterointi/transcribe_single_wav.sh` | whisper large-v3-turbo | `.wav` → `.txt` |
| [Kuva-analyysi](scripts/kuvat/) | cron 15 min (kontti) | `kuvat/analyze_images.sh` → `encode_image.py` | `MALLI_KUVAT` | kuva `**/Liitteet/`:ssä → `*_teksti.md` + linkit viereisiin md-tiedostoihin |
| [Kuvatekstien jalostus](scripts/kuvat/) | cron 5 min (kontti) | `kuvat/refine_image_texts.py` | `MALLI_TEKSTIT` | `*_teksti.md` joissa `#siisti-kuvailutulkkaus` → siistitty kuvaus + avainsanat |
| [Obsidian-notejen siistiminen](scripts/siistiminen/) | cron 1 min (kontti) | `siistiminen/cleanup_obsidian_notes.py` | `MALLI_TEKSTIT` | `*[siisti]*`-merkitty `.md` → korvattu sisältö |
| [Transkriptien siistiminen](scripts/siistiminen/) | manuaalinen (kontti) | `siistiminen/cleanup_transcripts.py [prompt]` | `MALLI_TEKSTIT` | `*[siisti]*`-merkitty `Nauhoitukset/*.md` + valittu prompt → `*_<prompt>.md` |
| [Kommentointi](scripts/puhe/) | manuaalinen (kontti) | `puhe/commenter.py` + VoxCPM2 | `MALLI_KOMMENTOIJA` | aktiivinen nauhoitusistunto → puhuttu kommentti |
| [YouTube-tiivistys](scripts/youtube/) | pi / manuaalinen (kontti) | `youtube/download_transcript.sh` → `tiivista_youtube.py` | **Mistral** | YouTube-linkki → litterointi + suomenkielinen tiivistelmä `Clippings/YouTube/` |
| [Verkkosivu-tiivistys](scripts/verkkosivu/) | pi / manuaalinen (kontti) | `verkkosivu/tallenna_verkkosivu.py` | **Mistral** | URL (robots.txt huomioiden) → tiivistelmä `Clippings/Verkkosivutiivistelmät/` |
| [PDF-tiivistys](scripts/pdf/) | pi / manuaalinen (kontti) | `pdf/tallenna_pdf.py` (pdftotext) | **Mistral** | PDF (URL tai vault-polku) → tiivistelmä `Clippings/PDF-tiivistelmät/` |
| [EU digital sovereignty -daily](scripts/eu_digital_sovereignty/) | cron (kontti) | `eu_digital_sovereignty/daily.py` | **Mistral** (tiivistys) + `MALLI_TEKSTIT` (valinta/tulkinta) | Staan-verkkohaku → Telegram-digesti + arkisto `Clippings/Staan/` |
| [Telegram-silta](scripts/telegram/) | jatkuva (kontti) | `telegram/telegram_bridge.py` | pi-agentti | Telegram-viestit → pi; linkit käsitellään determ. ennen pi:tä |

(Lisäksi `puhe/say.py` on yksinkertainen TTS-asiakas debugointiin, ei oma työnkulku. Julkisen datan tiivistys käyttää Mistralia; yksityinen vault-data käsitellään paikallisilla `MALLI_*`-malleilla.)

## Pikakäynnistys

### Esivaatimukset

- macOS Apple Silicon (Metal-tuki — Ollama ja whisper.cpp käyttävät GPU:ta)
- [Homebrew](https://brew.sh) — pakettienhallinta `brew install`-komentoja varten
- [Docker Desktop](https://docker.com/products/docker-desktop/) — `mactonus`-kontti pyörii sen päällä
- [Obsidian](https://obsidian.md) + vault-hakemisto johonkin

### 1. Asenna riippuvuudet

```bash
brew install whisper-cpp   # whisper-server + whisper-cli
brew install sox           # rec-komento nauhoitukseen
brew install ollama        # LLM-runtime (vaihtoehto: brew install --cask ollama-app GUI:lla)
```

### 2. Lataa Ollama-mallit

`ollama pull` vaatii että Ollama-daemoni on käynnissä. Voit aloittaa varsinaisen käynnistyksen jo nyt (ks. kohta 7) ja jättää sen päälle, tai aja tilapäisesti `ollama serve` toisessa terminaalissa pelkän pull-vaiheen ajaksi.

```bash
ollama pull gemma4:e4b     # multimodaali, kuva-analyysiin (MALLI_KUVAT)
ollama pull gemma4:31b     # iso, tekstit + kommentointi (MALLI_TEKSTIT, MALLI_KOMMENTOIJA)
```

`gemma4:31b` on iso (~19 GB) ja vaatii merkittävästi VRAM:ia. Jos muisti loppuu (whisperin ja VoxCPM2:n rinnalla), vaihda esim. `MALLI_KOMMENTOIJA='gemma4:e4b'` `.env`:ssä — kommentointi on reaaliaikaista ja kilpailee VoxCPM2:n kanssa muistista.

### 3. Lataa whisper-malli

```bash
mkdir -p conf/whisper-models
curl -L -o conf/whisper-models/ggml-large-v3-turbo.bin \
    https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin
```

### 4. Konfiguroi `.env`

```bash
cp .env.example .env
```

Aseta vähintään `VAULT_HOST_PATH` (Obsidian-vaultin absoluuttinen polku) ja `MALLI_*`-arvot kohdasta 2. Muut säädöt toimivat oletuksilla. Julkisen datan tiivistys (YouTube/verkkosivu/PDF/EU-daily) vaatii lisäksi `MISTRAL_API_KEY`:n; valinnaiset `STAAN_API_KEY` (EU-daily) ja `TELEGRAM_BOT_TOKEN` (Telegram-silta) ohjeineen `.env.example`:ssä.

### 5. Luo kehotetiedostot vaultiin

Skriptit lukevat kehotteet vaultista ajonaikaisesti. Luo nämä `.md`-tiedostot ennen ensimmäistä ajoa — sisältö on prompt LLM:lle:

| Tiedosto | Käyttäjä | Pakollinen? |
|---|---|---|
| `<vault>/mactonus/Kehotteet/Analysoi kuva.md` | `encode_image.py` (kuva-analyysi) | optionaali — falbackaa inline-defaulttiin |
| `<vault>/mactonus/Kehotteet/Kommentoija.md` | `commenter.py` (kommentointi) | **pakollinen** kommentointiin |
| `<vault>/mactonus/Dokumenttimuoto-kehotteet/<nimi>.md` | `cleanup_transcripts.py [nimi]` | **pakollinen** annetulle prompt-nimelle |

`cleanup_obsidian_notes.py`:n kehote on inline-koodissa eikä vaadi tiedostoa.

### 6. VoxCPM2-palvelin äänikommentointia varten

Kommentointi-työnkulku (`puhe/commenter.py` + `say.py`) käyttää erillistä TTS-palvelinta ([`paikallinen-puheassistentti`](https://github.com/atonusgit/paikallinen-puheassistentti)), joka kuuntelee portissa 8179. Se on oma reponsa, mutta tarkoitettu osaksi mactonus-kokonaisuutta — kloonataan mactonus-juuren sisään.

Mactonus-juuressa:
```bash
git clone https://github.com/atonusgit/paikallinen-puheassistentti
cd paikallinen-puheassistentti
python3 -m venv .venv
source .venv/bin/activate
pip3 install -r requirements.txt          # ks. projektin oma README tarkemmista ohjeista
```

Palvelimen käynnistys on kohdassa 7.

### 7. Käynnistä palvelut

Neljä terminaalia. A jää auki missä tahansa, B–D ajetaan mactonus-juuressa:

```bash
# A. Ollama LLM-runtime — :11434 (jää auki)
OLLAMA_HOST=0.0.0.0 OLLAMA_KEEP_ALIVE=24h ollama serve

# B. whisper.cpp server — :8178 (jää auki)
bash scripts/litterointi/whisper_server.sh

# C. VoxCPM2 server — :8179 (jää auki)
cd paikallinen-puheassistentti
source .venv/bin/activate
python3 voxcpm2_server.py

# D. mactonus-kontti
docker compose up -d --build
```

Ollaman env-muuttujat:
- `OLLAMA_HOST=0.0.0.0` — sitoutuu kaikkiin verkkointerface-osoitteisiin niin että `host.docker.internal:11434` toimii kontista varmasti (default `127.0.0.1` voi jäädä kontille tavoittamattomiin riippuen Dockerin verkkotilasta).
- `OLLAMA_KEEP_ALIVE=24h` — pitää mallit VRAM:ssa 24 h. Default 5 min aiheuttaisi mallien cold-loadia 1–15 min välein (cron-työnkulut), jolloin iso 31B-malli takkuilee.

Vaihtoehto on `brew services start ollama`, mutta se käynnistää Ollaman default-asetuksilla — env-muuttujien asettaminen vaatii LaunchAgent-plistin muokkausta.

Kontti tavoittaa hostin palvelimet (Ollama, whisper, VoxCPM2) `host.docker.internal`-osoitteen kautta — ei tarvetta säätää portteja erikseen.

Nauhoituksen ajokomennot: ks. [`scripts/litterointi/`](scripts/litterointi/).

## Hakemistorakenne

```
mactonus/
├── Dockerfile                 # kontti-image: cron + Python + Node/pi + poppler-utils
├── docker-compose.yml         # mount /vault + .pi + extra_hosts host.docker.internal
├── scripts/
│   ├── config.py              # MALLI_*, OLLAMA_*, WHISPER_*, VOXCPM_*, MISTRAL_* — keskitetty
│   ├── mistral_apu.py         # jaettu: Mistral-kutsu + tiivistyskehote + frontmatter-muoto
│   ├── verkko_apu.py          # jaettu: robots + haku + HTML→teksti + meta
│   ├── tiedosto_apu.py        # jaettu: tiedostonimien siistiminen (säilyttää ääkköset)
│   ├── litterointi/           # HOST: nauhoitus + whisper              → README
│   ├── kuvat/                 # KONTTI cron: kuva-analyysi             → README
│   ├── siistiminen/           # KONTTI: muistiinpanot + transkriptit   → README
│   ├── puhe/                  # KONTTI: kommentointi + TTS             → README
│   ├── youtube/               # tiivistys (Mistral)                    → README
│   ├── verkkosivu/            # tiivistys (Mistral)                    → README
│   ├── pdf/                   # tiivistys (Mistral, pdftotext)         → README
│   ├── eu_digital_sovereignty/ # cron: Staan + Mistral daily           → README
│   ├── telegram/              # pi-silta                               → README
│   ├── lamppu/ ssh/ staan/ tilauspalvelu/      # agentin skill-skriptit (kuvattu .pi:n SKILL.md:issä)
│   └── aihe_seuraaja/ cron/ muisti/ pi_vault_sync/ yhteenveto/  # muut työnkulut
├── conf/
│   ├── cron/                  # cron-tiedostot (bind-mount /etc/cron.d/:hen)
│   └── whisper-models/        # ggml-*.bin (gitignore)
├── .pi/                       # erillinen repo: agentin äly (skillit/muisti/malli) — gitignore
├── paikallinen-puheassistentti/   # erillinen host-projekti: voxcpm2_server.py + voices/
└── logs/                      # cron-ajojen tulosteet (host-mount)
```

## Polkuhuomioita

Skriptit viittaavat **konttisisäisiin** polkuihin (`/vault`, `/root/scripts/<työnkulku>/...`). Host-puolella nämä ovat Obsidian-vault ja `mactonus/scripts/`. Kontti ↔ host -mapit `docker-compose.yml`:ssä.

`scripts/litterointi/`-kansion skriptit ajetaan nativisti hostilla — ne olettavat `/opt/homebrew/bin/rec`, `/opt/homebrew/bin/sox` ja `whisper-server` PATHissa. Niiden väliset polut ratkaistaan `BASH_SOURCE`:n kautta, joten repo voi olla missä tahansa host-kansiossa.

## Konfiguraatio

Pysyvä infra (URL:t, portit, timeoutit) on `scripts/config.py`:ssä. Usein vaihtuvat arvot (mallit, vault-polku, äänireferenssi) ja salaisuudet (API-avaimet, tokenit) tulevat `.env`-tiedostosta — kopioi `.env.example` → `.env` ja täytä `VAULT_HOST_PATH`. Python-skriptit `from config import ...`; bash-skriptit `eval "$(python3 ../config.py)"`. Älä hajauta arvoja takaisin skripteihin, äläkä kovakoodaa salaisuuksia (tämä repo on julkinen) — ne tulevat aina `.env`:stä.
