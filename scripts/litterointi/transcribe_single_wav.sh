#!/bin/bash

SKRIPTIT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
eval "$(python3 "$SKRIPTIT/../config.py")"

if [ -z "$1" ]; then
    echo "Käyttö: bash transcribe_single_wav.sh <tiedosto.wav>"
    exit 1
fi

TIEDOSTO="$1"

if [ ! -f "$TIEDOSTO" ]; then
    printf "\033[1;31m✗ Tiedostoa ei löydy:\033[0m %s\n" "$TIEDOSTO"
    exit 1
fi

if ! curl -s --max-time 2 -o /dev/null "$WHISPER_URL" 2>/dev/null; then
    printf "\033[1;31m✗ Whisper-server ei vastaa osoitteessa %s\033[0m\n" "$WHISPER_URL" >&2
    printf "  Käynnistä ensin whisper_server.sh\n" >&2
    exit 1
fi

printf "\033[1;33m⟳ Litteroidaan:\033[0m %s\n" "$TIEDOSTO"

TXT="${TIEDOSTO%.wav}.txt"
if curl -sfS -X POST "$WHISPER_URL" \
        -F "file=@$TIEDOSTO" \
        -F "response_format=text" \
        -F "language=fi" \
        -o "$TXT"; then
    printf "\033[1;32m✓ Valmis:\033[0m %s\n" "$TXT"
else
    rm -f "$TXT"
    printf "\033[1;31m✗ Litterointi epäonnistui (onko whisper-server pystyssä osoitteessa %s?)\033[0m\n" "$WHISPER_URL"
    exit 1
fi
