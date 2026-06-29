# Mactonus-skriptien yhteiset asetukset.
# Pysyvä infra (URL:t, portit, timeoutit) tässä; usein vaihtuvat (mallit,
# äänireferenssi) ladataan .env-tiedostosta.
#
# Python-skriptit:  from config import OLLAMA_URL, ...
# Bash-skriptit:    eval "$(python3 "$SKRIPTIT/config.py")"
import os

# === Ollama (LLM-palvelin hostilla) ===
OLLAMA_URL = "http://host.docker.internal:11434/api/generate"
OLLAMA_AIKAKATKAISU = 300  # iso malli (esim. 31B) voi viedä >3 min cold-loadissa

# Mallit luetaan .env:stä; defaultit toimivat ilman .env-merkintöjä.
MALLI_KUVAT = os.environ.get("MALLI_KUVAT", "gemma4:e4b")              # encode_image.py
MALLI_TEKSTIT = os.environ.get("MALLI_TEKSTIT", "gemma4:31b")          # cleanup_*, rename_file.py
MALLI_KOMMENTOIJA = os.environ.get("MALLI_KOMMENTOIJA", "gemma4:31b")  # commenter.py

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
# Yhden nauhoituspätkän pituus sekunteina (record_and_transcribe.sh).
NAUHOITUS_PATKA_PITUUS = int(os.environ.get("NAUHOITUS_PATKA_PITUUS", "120"))
# Kommentoijan kynnys: kuinka monta uutta litteroitua pätkää tarvitaan
# ennen kuin commenter.py kutsuu Ollamaa + VoxCPM2:ta.
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
