#!/bin/bash

URL="${1:-}"

[ -z "$URL" ] && { echo "Usage: $0 <youtube-url>"; return 1 2>/dev/null || false; }

# Hae otsikko, julkaisupäivä ja kanava yhdellä kutsulla (kolme --print-riviä).
META=$(yt-dlp --skip-download --print "%(title)s" --print "%(upload_date)s" --print "%(uploader)s" "$URL" 2>/dev/null)
# Korvaa vain tiedostojärjestelmässä kielletyt merkit; ääkköset säilyvät (vrt. tiedosto_apu.py).
TITLE=$(printf '%s\n' "$META" | sed -n '1p' | tr -d '\n' | sed 's#[<>:"/\\|?*]#_#g')
[ -z "$TITLE" ] && { echo "Failed to get video title"; return 1 2>/dev/null || false; }

# upload_date on muotoa YYYYMMDD (tai NA). Julkaisupäivä jos saatavilla, muuten tallennuspäivä.
UPLOAD=$(printf '%s\n' "$META" | sed -n '2p')
if printf '%s' "$UPLOAD" | grep -qE '^[0-9]{8}$'; then
    PVM="${UPLOAD:0:4}-${UPLOAD:4:2}-${UPLOAD:6:2}"
else
    PVM="$(date +%F)"
fi

# Kanava julkaisijaksi; fallback "YouTube" jos puuttuu.
UPLOADER=$(printf '%s\n' "$META" | sed -n '3p')
case "$UPLOADER" in ""|NA) UPLOADER="YouTube";; esac

mkdir -p "/vault/Clippings/YouTube"

TEMP_DIR=$(mktemp -d)
TEMP_BASE="$TEMP_DIR/transcript"
FINAL_MD="/vault/Clippings/YouTube/${TITLE}.md"

find_subtitle() {
    ls "$TEMP_DIR"/transcript.*.srt "$TEMP_DIR"/transcript.*.vtt 2>/dev/null | head -1
}

# Try different subtitle options (convert to srt — widely supported by yt-dlp)
# 1. Try original English subtitles
yt-dlp --write-subs --sub-lang en-orig --convert-subs srt --skip-download --output "$TEMP_BASE" "$URL" 2>/dev/null
# 2. Try English subtitles
[ -z "$(find_subtitle)" ] && yt-dlp --write-subs --sub-lang en --convert-subs srt --skip-download --output "$TEMP_BASE" "$URL" 2>/dev/null
# 3. Try auto-generated English
[ -z "$(find_subtitle)" ] && yt-dlp --write-auto-sub --sub-lang en --convert-subs srt --skip-download --output "$TEMP_BASE" "$URL" 2>/dev/null
# 4. Try any auto-generated
[ -z "$(find_subtitle)" ] && yt-dlp --write-auto-sub --convert-subs srt --skip-download --output "$TEMP_BASE" "$URL" 2>/dev/null
# 5. Try any manual subtitles
[ -z "$(find_subtitle)" ] && yt-dlp --write-subs --convert-subs srt --skip-download --output "$TEMP_BASE" "$URL" 2>/dev/null

TEMP_SUB=$(find_subtitle)

if [ -z "$TEMP_SUB" ] || [ ! -s "$TEMP_SUB" ]; then
    echo "No transcript available for: $TITLE"
    echo "Available subtitles:"
    yt-dlp --list-subs "$URL" 2>/dev/null | head -20
    rm -rf "$TEMP_DIR"
    return 1 2>/dev/null || false
fi

# Välitiedosto tiivistäjälle: metadata-header + "---" + litteroitu teksti (SRT/VTT-
# aikaleimat ja sekvenssinumerot riisuttu). tiivista_youtube.py kirjoittaa tästä lopullisen
# muodon (frontmatter + tiivistelmä) eikä säilytä litterointia.
{
    echo "# $TITLE"
    echo "Lähde: $URL"
    echo "Päiväys: $PVM"
    echo "Julkaisija: $UPLOADER"
    echo ""
    echo "---"
    echo ""
    grep -v '^[0-9]*$' "$TEMP_SUB" \
        | grep -v '^[0-9][0-9]:[0-9][0-9]:[0-9][0-9]' \
        | grep -v '^WEBVTT' \
        | grep -v '^$' \
        | sed 's/<[^>]*>//g'
} > "$FINAL_MD"

rm -rf "$TEMP_DIR"

# Tiivistä litterointi suomeksi (Mistral) ja kirjoita lopullinen muoto. Best-effort: jos
# Mistral ei vastaa, välitiedosto (litterointi) jää talteen sellaisenaan uusintaa varten.
python3 "$(dirname "$0")/tiivista_youtube.py" "$FINAL_MD" || echo "Tiivistys ohitettiin (Mistral ei vastannut)."

echo "Saved to: $FINAL_MD"
