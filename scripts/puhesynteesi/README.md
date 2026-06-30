# Puhesynteesi (TTS) — VoxCPM2-palvelin

Host-puolella ajettava puhesynteesipalvelin (text-to-speech), joka syntetisoi suomenkielistä
puhetta käyttäjän ääni­referenssin mukaisesti. Mactonuksen kommentointi (`scripts/kommentointi/`) on sen
**asiakas** verkon yli: `host.docker.internal:8179`. Palvelin pyörii hostilla (Metal-GPU), ei
kontissa — kuten llama.cpp ja whisper.cpp.

(Aiemmin oma repo `paikallinen-puheassistentti`; absorboitu osaksi mactonusta. Vain TTS-palvelin
tuotiin — entinen LLM-pohjainen "assistentti" jätettiin pois.)

## Asennus (host)

```bash
brew install sox python@3.12
cd scripts/puhesynteesi
python3.12 -m venv .venv
source .venv/bin/activate
pip3 install voxcpm soundfile requests numpy
```

## Nauhoita oma ääni (kerran)

```bash
source .venv/bin/activate && python3 nauhoita_aani.py
```

Tallentaa wav:n `voices/`-kansioon. Aseta sen nimi `.env`:hen: `VOXCPM_REFERENSSI=<nimi>.wav`.

## Käynnistä palvelin

```bash
source .venv/bin/activate && python3 voxcpm2_palvelin.py
```

Kuuntelee `127.0.0.1:8179`. Kontti tavoittaa sen `host.docker.internal:8179`-aliaksella (ei
porttisäätöjä). Lataa VoxCPM2-mallin kerran muistiin.

## Tiedostot

- `voxcpm2_palvelin.py` — HTTP-palvelin, syntetisoi ja (valinnaisesti) soittaa puheen
- `aanivalitsin.py` — `voices/`-kansion referenssiäänien resolvointi/valinta (`resolve_ref`)
- `nauhoita_aani.py` — äänireferenssin nauhoitus

`voices/`, `output/` ja `.venv/` ovat host-paikallisia eikä niitä versioida (gitignore).
