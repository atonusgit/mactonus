#!/bin/bash
# Nauhoittaa 2min-pätkiä ja litteroi ne taustalla per pätkä.
# Ctrl+C:n jälkeen kutsuu litteroi_istunto.sh:ta joka viimeistelee ja kokoaa .md:n.

set -u
SKRIPTIT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
set -a; source "$SKRIPTIT/../../.env"; set +a
eval "$(python3 "$SKRIPTIT/../config.py")"

VAULT="$VAULT_HOST_PATH"
KANSIO="$VAULT/mactonus/Nauhoitukset"

tarkista_whisper() {
    if ! curl -s --max-time 2 -o /dev/null "$WHISPER_URL" 2>/dev/null; then
        printf "\033[1;31m✗ Whisper-server ei vastaa osoitteessa %s\033[0m\n" "$WHISPER_URL" >&2
        printf "  Käynnistä ensin whisper_palvelin.sh\n" >&2
        exit 1
    fi
}

tarkista_whisper

SESSIO="$(date '+%Y-%m-%d_%H-%M-%S')"
TEMP="$KANSIO/tmp_chunks/$SESSIO"
INDEKSI=0

mkdir -p "$TEMP"

litteroi() {
    printf "\033[1;33m⟳ Litteroidaan $(basename "$1")...\033[0m\n"
    local chunk=$1
    local txt="${chunk%.wav}.txt"
    curl -sfS -X POST "$WHISPER_URL" \
        -F "file=@$chunk" \
        -F "response_format=text" \
        -F "language=fi" \
        -o "$txt" 2>/dev/null \
        || rm -f "$txt"
}

viimeistele() {
    # rec kirjoittaa keskeneräisenkin .wav:n valmiiksi SIGINT:n jälkeen, joten
    # se säilytetään ja litteroi_istunto.sh litteroi sen muiden mukana.
    echo ""
    bash "$SKRIPTIT/litteroi_istunto.sh" "$SESSIO"
    exit $?
}

trap viimeistele INT

printf "\033[1;31m● NAUHOITETAAN\033[0m – Lopeta Ctrl+C\n"
printf "\033[0;37m%s\033[0m\n" "$TEMP"
echo ""

while true; do
    CHUNK="$TEMP/${SESSIO}_$(printf '%03d' $INDEKSI).wav"
    /opt/homebrew/bin/rec --buffer 524288 -r 16000 -c 1 -b 16 "$CHUNK" trim 0 "$NAUHOITUS_PATKA_PITUUS"
    litteroi "$CHUNK" &
    INDEKSI=$((INDEKSI + 1))
done
