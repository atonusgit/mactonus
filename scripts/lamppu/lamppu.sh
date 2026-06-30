#!/usr/bin/env bash
# lamppu.sh — Keittiön lampun hallinta
#
# Käyttö:
#   lamppu.sh päälle   → sytyttää lampun
#   lamppu.sh pois     → sammuttaa lampun
#   lamppu.sh status   → näyttää JSON-vastauksen

set -euo pipefail

WEBHOOK="${N8N_WEBHOOK_URL:?N8N_WEBHOOK_URL is not set.}"
OTSAKE="${N8N_WEBHOOK_HEADER:?N8N_WEBHOOK_HEADER is not set.}"
STATUS="true"

case "${1:-}" in
    pois)       STATUS="false" ;;
    päälle)     STATUS="true" ;;
    *)          echo "Käyttö: $0 <päälle> | <pois>" >&2; exit 1 ;;
esac

curl -s -X POST -d "id=1&status=${STATUS}" -H "$OTSAKE" "$WEBHOOK"
