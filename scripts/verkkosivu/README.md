# Verkkosivu-tiivistys

URL → robots.txt-tarkistus → haku + HTML→teksti → suomenkielinen tiivistelmä (Mistral) → `Clippings/Verkkosivutiivistelmät/<otsikko>.md`.

```mermaid
flowchart LR
    URL([URL]) --> R{robots.txt<br/>sallii?}
    R -->|ei| X[ohita]
    R -->|kyllä| F["hae_html + html_tekstiksi<br/>(verkko_apu.py)"]
    F --> S["tallenna_verkkosivu.py"]
    S -->|Mistral| MD["Clippings/Verkkosivutiivistelmät/<br/>frontmatter + tiivistelmä"]
```

## Skriptit

- `tallenna_verkkosivu.py` — robots-tarkistus, haku, HTML→teksti, tiivistys, tallennus

## Jaettu logiikka

- **Kaavinta** (`verkko_apu.py`): `sivu_sallittu` (robots), `hae_html`, `html_tekstiksi`, `etsi_otsikko`, `etsi_julkaisija`, `etsi_julkaisupvm` — jaettu **EU-daily**:n kanssa.
- **Tiivistys + muotoilu** (`mistral_apu.py`): jaettu **YouTube-** ja **PDF-tiivistyksen** kanssa, sama frontmatter-muoto. Alkuperäistä sisältöä ei säilytetä.
