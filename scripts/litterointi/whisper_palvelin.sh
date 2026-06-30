#!/bin/bash
# Käynnistää whisper.cpp -palvelimen hostilla Metal-kiihdytyksellä.
# Pidä terminaali-ikkuna auki; Ctrl+C sammuttaa palvelimen.

SKRIPTIT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
eval "$(python3 "$SKRIPTIT/../config.py")"

MALLI_KANSIO="$SKRIPTIT/../../conf/whisper-models"
MALLI="$MALLI_KANSIO/$WHISPER_MALLI"

if [ ! -f "$MALLI" ]; then
    printf "\033[1;31m✗ Mallia ei löydy:\033[0m %s\n" "$MALLI"
    printf "Lataa se:\n"
    printf "  mkdir -p %s\n" "$MALLI_KANSIO"
    printf "  cd %s\n" "$MALLI_KANSIO"
    printf "  curl -LO https://huggingface.co/ggerganov/whisper.cpp/resolve/main/%s\n" "$WHISPER_MALLI"
    exit 1
fi

if ! command -v whisper-server >/dev/null 2>&1; then
    printf "\033[1;31m✗ whisper-server ei löydy PATH:sta\033[0m\n"
    printf "Asenna: brew install whisper-cpp\n"
    exit 1
fi

if lsof -iTCP:"$WHISPER_PORTTI" -sTCP:LISTEN >/dev/null 2>&1; then
    printf "\033[1;33m⚠ Portti %s on jo käytössä — palvelin todennäköisesti jo pystyssä\033[0m\n" "$WHISPER_PORTTI"
    exit 1
fi

printf "\033[1;32m● WHISPER-SERVER käynnistyy\033[0m – malli: %s, portti: %s\n" "$(basename "$MALLI")" "$WHISPER_PORTTI"
printf "\033[0;37mLopeta Ctrl+C\033[0m\n\n"

exec whisper-server \
    -m "$MALLI" \
    --host "$WHISPER_HOST" \
    --port "$WHISPER_PORTTI" \
    -l "$WHISPER_KIELI"
