#!/bin/bash

LOCK=/tmp/analysoi_kuvat.lock
MAKSIMI=20

if [ -f "$LOCK" ]; then
    echo "$(date): Edellinen ajo vielä kesken, ohitetaan."
    exit 0
fi

touch "$LOCK"
trap "rm -f $LOCK" EXIT

echo "$(date): Aloitetaan kuvien analysointi"

LASKURI=0

while IFS= read -r kuva; do
    KUVA_NIMI=$(basename "$kuva")
    KUVA_KANSIO=$(dirname "$kuva")
    KUVA_POHJA="${KUVA_NIMI%.*}"
    ANALYYSI_MD="$KUVA_KANSIO/${KUVA_POHJA}_teksti.md"
    YLAKANSIO=$(dirname "$KUVA_KANSIO")

    if [ -f "$ANALYYSI_MD" ]; then
        echo "$(date): Ohitetaan (jo analysoitu): $kuva → $ANALYYSI_MD"
        continue
    fi

    if [ $LASKURI -ge $MAKSIMI ]; then
        echo "$(date): Maksimi ($MAKSIMI kuvaa) saavutettu."
        break
    fi

    echo "$(date): Analysoidaan: $kuva"

    TULOS=$(timeout 120 python3 /root/scripts/kuvat/enkoodaa_kuva.py "$kuva" "$ANALYYSI_MD" 2>&1)
    echo "$TULOS"
    UUSI_POHJA=$(echo "$TULOS" | grep "^UUSI_POHJA:" | cut -d: -f2)

    if [ -n "$UUSI_POHJA" ]; then
        LINKKI_POHJA="$UUSI_POHJA"
        KUVA_EXT=".${kuva##*.}"
        UUSI_KUVA_NIMI="${UUSI_POHJA%_teksti}${KUVA_EXT}"
        HAKU_NIMI="$UUSI_KUVA_NIMI"
    else
        LINKKI_POHJA="${KUVA_POHJA}_teksti"
        HAKU_NIMI="$KUVA_NIMI"
    fi

    echo "DEBUG: HAKU_NIMI=$HAKU_NIMI"
    echo "DEBUG: YLAKANSIO=$YLAKANSIO"
    echo "DEBUG: LINKKI_POHJA=$LINKKI_POHJA"
    find "$YLAKANSIO" -maxdepth 1 -name "*.md" -type f

    while IFS= read -r md; do

        echo "DEBUG: Tarkistetaan $md"
        if grep -q "$HAKU_NIMI" "$md" 2>/dev/null; then
            MD_KANSIO=$(dirname "$md")
            SUHTEELLINEN=$(python3 -c "import os; print(os.path.relpath('$KUVA_KANSIO', '$MD_KANSIO'))")
            LINKKI="[[${SUHTEELLINEN}/${LINKKI_POHJA}]]"
            sed -i "s|!\[\[${HAKU_NIMI}\]\]|![[${HAKU_NIMI}]]\n${LINKKI}|g" "$md"
            echo "$(date): Lisätty linkki: $md → ${LINKKI}"
        fi
    done < <(find "$YLAKANSIO" -maxdepth 1 -name "*.md" -type f)

    LASKURI=$((LASKURI + 1))
done < <(find /vault -path "*/Liitteet/*" -type f \( -name "*.png" -o -name "*.jpg" -o -name "*.jpeg" \))

echo "$(date): Valmis. Analysoitiin $LASKURI kuvaa."