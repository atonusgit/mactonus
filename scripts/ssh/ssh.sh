#!/usr/bin/env bash
# ssh.sh — geneerinen SSH-yhteys: host annetaan argumenttina ja se vastaa
# ~/.ssh/config:in määrittelyä. Tuettujen hostien tieto on agentin (yksityisessä)
# SKILL.md:ssä, ei tässä skriptissä. DynDNS-fallback (-d) lukee tunnukset env:stä.

set -euo pipefail

USE_DYNDNS=false

# Valinnainen -d / --dyndns
if [[ "$1" == -d || "$1" == --dyndns ]]; then
    USE_DYNDNS=true
    shift
fi

if [ $# -eq 0 ] || [ "${1:-}" == -d ] || [ "${1:-}" == --dyndns ]; then
    echo "Käyttö: $0 [-d] <host> [komennon osa...]" >&2
    echo "Host vastaa ~/.ssh/config-määrittelyä (sallitut hostit: ks. agentin SKILL.md)." >&2
    exit 1
fi

HOST="$1"
shift

# Jos käytössä DynDNS, hae IP ja ohita SSH-config
if $USE_DYNDNS; then
    ip=$(curl -sL -u "$DYNDNS_USER:$DYNDNS_PASS" "$DYNDNS_URL" | tr -d '[:space:]')
    if [ -z "$ip" ]; then
        echo "Virhe: IP-osoitetta ei saatu dyndns-palvelusta." >&2
        exit 1
    fi
    ssh -p "$DYNDNS_PORT" -o StrictHostKeyChecking=accept-new "${SSH_USER}@$ip" "${@:-}"
    exit 0
fi

ssh "$HOST" "${@:-}"
