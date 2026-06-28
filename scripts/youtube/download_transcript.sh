#!/bin/bash

URL="${1:-}"

[ -z "$URL" ] && { echo "Usage: $0 <youtube-url>"; return 1 2>/dev/null || false; }

TITLE=$(yt-dlp --get-title "$URL" 2>/dev/null | tr -d '\n' | sed 's/[^a-zA-Z0-9 _.,-]/_/g')
[ -z "$TITLE" ] && { echo "Failed to get video title"; return 1 2>/dev/null || false; }

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

# Strip SRT/VTT timestamps and sequence numbers, keep only text lines
{
    echo "# $TITLE"
    echo ""
    echo "Lähde: $URL"
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

# Tiivistä litterointi suomeksi (Ollama) ja kirjoita tiivistelmä + litterointi samaan
# tiedostoon. Best-effort: litterointi on jo tallessa, joten jos Ollama ei vastaa,
# tiedosto jää litteroinniksi sellaisenaan.
python3 "$(dirname "$0")/tiivista_youtube.py" "$FINAL_MD" || echo "Tiivistys ohitettiin (Ollama ei vastannut)."

echo "Saved to: $FINAL_MD"
