#!/bin/bash
# Viimeistelee nauhoitusistunnon: litteroi puuttuvat pätkät, kokoaa .md:n,
# nimeää sen AI-mallilla ja siivoaa istuntokansion vain jos kaikki onnistui.
# Käyttö:
#   bash transcribe_session.sh 2026-04-23_14-03-17

set -u

SESSIO="${1:-}"
if [ -z "$SESSIO" ]; then
    echo "Käyttö: $0 <SESSIO>" >&2
    echo "Esim:  $0 2026-04-23_14-03-17" >&2
    exit 1
fi

SKRIPTIT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
set -a; source "$SKRIPTIT/../../.env"; set +a
eval "$(python3 "$SKRIPTIT/../config.py")"

VAULT="$VAULT_HOST_PATH"
KANSIO="$VAULT/mactonus/Nauhoitukset"
TEMP="$KANSIO/tmp_chunks/$SESSIO"
LOPULLINEN="$KANSIO/$SESSIO.md"

if ! curl -s --max-time 2 -o /dev/null "$WHISPER_URL" 2>/dev/null; then
    printf "\033[1;31m✗ Whisper-server ei vastaa osoitteessa %s\033[0m\n" "$WHISPER_URL" >&2
    printf "  Käynnistä ensin whisper_server.sh\n" >&2
    exit 1
fi

if [ ! -d "$TEMP" ]; then
    echo "Istunnon kansio puuttuu: $TEMP" >&2
    exit 1
fi

shopt -s nullglob
WAVIT=("$TEMP/${SESSIO}_"*.wav)
shopt -u nullglob

if [ ${#WAVIT[@]} -eq 0 ]; then
    echo "Ei wav-tiedostoja istunnolle $SESSIO" >&2
    exit 1
fi

# Yhdistä wav-pätkät backupiksi (kerran per istunto, ei ylikirjoiteta)
BACKUP_WAV="$KANSIO/${SESSIO}.wav"
if [ ! -f "$BACKUP_WAV" ]; then
    printf "\033[1;33m⟳ Yhdistetään wav-tiedostot backupiksi...\033[0m\n"
    /opt/homebrew/bin/sox "${WAVIT[@]}" "$BACKUP_WAV"
    printf "\033[0;37mBackup: %s\033[0m\n" "$BACKUP_WAV"
fi

echo ""
printf "\033[1;33m⟳ Litteroidaan puuttuvat pätkät...\033[0m\n"

# Kerää wavit joilla ei ole ei-tyhjää .txt-paria ja litteroi kukin whisper-serverillä.
# Persistenttipalvelin pitää mallin muistissa, joten peräkkäiset HTTP-kutsut ovat halpoja.
LITTEROITAVAT=()
for wav in "${WAVIT[@]}"; do
    txt="${wav%.wav}.txt"
    if [ ! -s "$txt" ]; then
        [ -f "$txt" ] && rm -f "$txt"
        LITTEROITAVAT+=("$wav")
        echo "Jonossa: $(basename "$wav")"
    fi
done

if [ ${#LITTEROITAVAT[@]} -gt 0 ]; then
    loki="/tmp/whisper-istunto-${SESSIO}.log"
    : > "$loki"
    for wav in "${LITTEROITAVAT[@]}"; do
        txt="${wav%.wav}.txt"
        echo "--- $(basename "$wav") ---" >> "$loki"
        if ! curl -sfS -X POST "$WHISPER_URL" \
                -F "file=@$wav" \
                -F "response_format=text" \
                -F "language=fi" \
                -o "$txt" 2>>"$loki"; then
            printf "\033[0;31m✗ Whisper-kutsu feilasi: %s (ks. %s)\033[0m\n" "$(basename "$wav")" "$loki"
            rm -f "$txt"
        fi
    done
fi

# Huomauta hiljaisista/tyhjiksi jääneistä pätkistä, mutta älä kaada ajoa eikä merkitse .md:hen
HILJAISET=()
for wav in "${WAVIT[@]}"; do
    txt="${wav%.wav}.txt"
    if [ ! -s "$txt" ]; then
        HILJAISET+=("$(basename "$wav")")
    fi
done

if [ ${#HILJAISET[@]} -gt 0 ]; then
    printf "\033[0;37mHiljaisia pätkiä skipataan: %s\033[0m\n" "${HILJAISET[*]}"
fi

# Kokoa lopullinen .md ja ohita tyhjät .txt:t
echo "# Nauhoitus $SESSIO" > "$LOPULLINEN"
echo "" >> "$LOPULLINEN"

shopt -s nullglob
for txt in "$TEMP/${SESSIO}_"*.txt; do
    [ -s "$txt" ] || continue
    cat "$txt" >> "$LOPULLINEN"
    echo "" >> "$LOPULLINEN"
done
shopt -u nullglob

# Varmista että .md ei jäänyt pelkäksi otsikoksi
if [ "$(wc -l < "$LOPULLINEN")" -le 2 ]; then
    printf "\033[0;31m✗ Lopullinen .md jäi tyhjäksi, istuntokansio säilytetään: %s\033[0m\n" "$TEMP"
    rm -f "$LOPULLINEN"
    exit 1
fi

# Kaikki OK → siivoa istuntokansio
rm -rf "$TEMP"

UUSI=$(python3 "$SKRIPTIT/rename_file.py" "$LOPULLINEN" "$SESSIO" "$KANSIO")
printf "\033[1;32m✓ Valmis:\033[0m %s\n" "${UUSI:-$LOPULLINEN}"
