#!/usr/bin/env bash
# Staan Answer - generates AI-powered grounded answers via Staan API
# Usage: staan-answer.sh <question> [--language fr] [--stream] [--related-queries] [--mode short|long] [--raw]  [--no-query-rewrite]

set -euo pipefail

API_URL="https://api.staan.ai/v2/answer"
API_KEY="${STAAN_API_KEY:?STAAN_API_KEY is not set.}"

usage() {
  cat <<EOF
Usage: $0 <question> [options]

Arguments:
  question    User question (required)

Options:
  --language lang     Answer language (default: fr). Currently only "fr" is supported
  --stream            Stream the response as Server-Sent Events
  --related-queries   Include follow-up question suggestions
  --mode short|long   Response length (default: short)
  --no-query-rewrite  Disable query rewriting before search
  --raw               Output raw response (no pretty-print)
  -h, --help          Show this help message
EOF
  exit 0
}

QUESTION=""
LANGUAGE="fr"
STREAM="false"
RELATED_QUERIES="false"
MODE="short"
QUERY_REWRITE="true"
RAW="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      ;;
    --language)
      LANGUAGE="$2"
      shift 2
      ;;
    --stream)
      STREAM="true"
      shift
      ;;
    --related-queries)
      RELATED_QUERIES="true"
      shift
      ;;
    --mode)
      MODE="$2"
      shift 2
      ;;
    --no-query-rewrite)
      QUERY_REWRITE="false"
      shift
      ;;
    --raw)
      RAW="true"
      shift
      ;;
    -*)
      echo "Unknown option: $1" >&2
      usage
      ;;
    *)
      if [[ -z "$QUESTION" ]]; then
        QUESTION="$1"
      else
        QUESTION="$QUESTION $1"
      fi
      shift
      ;;
  esac
done

if [[ -z "$QUESTION" ]]; then
  echo "Error: question is required" >&2
  exit 1
fi

# Use python to build valid JSON and make the request via curl
JSON=$(python3 -c "
import json, sys
data = {
    'query': sys.argv[1],
    'mode': sys.argv[2],
    'language': sys.argv[3],
    'markdown': True,
    'query_rewrite': sys.argv[4] == 'true',
}
if sys.argv[5] == 'true':
    data['related_queries'] = True
print(json.dumps(data))
" "$QUESTION" "$MODE" "$LANGUAGE" "$QUERY_REWRITE" "$RELATED_QUERIES")

if [[ "$STREAM" == "true" ]]; then
  curl \
    --silent \
    --max-time 30 \
    --no-buffer \
    -H "Authorization: Bearer ${API_KEY}" \
    -H "Content-Type: application/json" \
    -X POST \
    -d "$JSON" \
    "$API_URL"
else
  RESPONSE=$(curl \
    --silent \
    --max-time 30 \
    -H "Authorization: Bearer ${API_KEY}" \
    -H "Content-Type: application/json" \
    -X POST \
    -d "$JSON" \
    "$API_URL")

  if [[ "$RAW" == "true" ]]; then
    echo "$RESPONSE"
  else
    echo "$RESPONSE" | python3 -c "import sys,json; print(json.dumps(json.load(sys.stdin), indent=2, ensure_ascii=False))"
  fi
fi
