# Mactonus-skriptien yhteiset asetukset.
# Pysyvä infra (URL:t, portit, timeoutit) tässä; usein vaihtuvat (mallit,
# äänireferenssi) ladataan .env-tiedostosta.
#
# Python-skriptit:  from config import LLM_URL, ...
#                   from llm_apu import kysy_llm   (jaettu LLM-kutsu)
# Bash-skriptit:    eval "$(python3 "$SKRIPTIT/config.py")"
import os

# === Paikallinen LLM (llama.cpp-palvelin hostilla, OpenAI-yhteensopiva /v1) ===
# Backendin vaihto = vain tämä URL. Sama formaatti käy muillekin
# OpenAI-yhteensopiville backendeille.
LLM_URL = "http://host.docker.internal:8080/v1/chat/completions"
LLM_AIKAKATKAISU = 300  # iso malli voi viedä useita minuutteja cold-loadissa

# Mallit luetaan .env:stä; defaultit toimivat ilman .env-merkintöjä.
# Router modessa nimen on täsmättävä serverin preset-id:hen tasan; -m -moodissa
# nimellä ei ole väliä. Pidetään täysi preset-id, niin molemmat toimivat.
MALLI_KUVAT = os.environ.get("MALLI_KUVAT", "unsloth/Qwen3.6-35B-A3B-MTP-GGUF:Q5_K_M")              # enkoodaa_kuva.py (kuva->teksti)
MALLI_TEKSTIT = os.environ.get("MALLI_TEKSTIT", "unsloth/Qwen3.6-35B-A3B-MTP-GGUF:Q5_K_M")          # siisti_*, nimea_tiedosto.py, paivittain.py
MALLI_KOMMENTOIJA = os.environ.get("MALLI_KOMMENTOIJA", "unsloth/Qwen3.6-35B-A3B-MTP-GGUF:Q5_K_M")  # kommentoija.py

# Kuvan max-reuna ennen vision-kutsua: pienennys välttää 413:n ja nopeuttaa
# (malli skaalaa kuvan kuitenkin). Nosta jos pieni teksti ei erotu OCR:ssä.
KUVA_MAKS_REUNA = int(os.environ.get("KUVA_MAKS_REUNA", "1536"))

# === Mistral (LLM-pilvipalvelu, käytetään YouTube-tiivistykseen) ===
MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"
MISTRAL_AIKAKATKAISU = 120
MISTRAL_MALLI = os.environ.get("MISTRAL_MALLI", "mistral-small-latest")  # tiivista_youtube.py
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "")

# === Whisper (whisper.cpp-palvelin hostilla, käytetään vain hostilta) ===
WHISPER_HOST = "127.0.0.1"
WHISPER_PORTTI = 8178
WHISPER_URL = f"http://{WHISPER_HOST}:{WHISPER_PORTTI}/inference"
WHISPER_KIELI = "fi"
WHISPER_MALLI = os.environ.get("WHISPER_MALLI", "ggml-large-v3-turbo.bin")

# === VoxCPM2 (TTS-palvelin hostilla, käytetään kontista) ===
VOXCPM_URL = "http://host.docker.internal:8179"
VOXCPM_AIKAKATKAISU = 180
VOXCPM_REFERENSSI = os.environ.get("VOXCPM_REFERENSSI", "anton.wav")

# === Nauhoitus & kommentointi ===
# Yhden nauhoituspätkän pituus sekunteina (nauhoita_ja_litteroi.sh).
NAUHOITUS_PATKA_PITUUS = int(os.environ.get("NAUHOITUS_PATKA_PITUUS", "120"))
# Kommentoijan kynnys: kuinka monta uutta litteroitua pätkää tarvitaan
# ennen kuin kommentoija.py kutsuu LLM:ää + VoxCPM2:ta.
KOMMENTOIJA_KYNNYS = int(os.environ.get("KOMMENTOIJA_KYNNYS", "1"))


if __name__ == "__main__":
    # Emittaa kaikki yllä olevat string/int/float-vakiot bash-yhteensopivina
    # exporteina, jotta bash-skriptit voivat sourceta ne:
    #   eval "$(python3 "$SKRIPTIT/config.py")"
    import shlex
    for _nimi, _arvo in sorted(globals().items()):
        if _nimi.startswith("_") or not isinstance(_arvo, (str, int, float)):
            continue
        print(f"export {_nimi}={shlex.quote(str(_arvo))}")
