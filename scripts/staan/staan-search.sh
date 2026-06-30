#!/usr/bin/env bash
# Staan Web Search - performs web searches via the Staan European Search API
# Usage: staan-search.sh <query> [market] [offset] [--extra-snippets] [--full-content] [--max-snippets N] [--min-score N] [--include-domains domain1,domain2] [--exclude-domains domain1,domain2] [--raw]

set -euo pipefail

API_URL="https://api.staan.ai/v2/search/web"
API_KEY="${STAAN_API_KEY:?STAAN_API_KEY is not set.}"

usage() {
  cat <<EOF
Usage: $0 <query> [market] [offset] [options]

Arguments:
  query     Search query (required)
  market    Market/locale (default: en-us). Options: en-us, fr-fr, de-de
  offset    Pagination offset (default: 0). Options: 0, 10, 20, 30

Options:
  --extra-snippets           Enable semantic chunk extraction (RAG)
  --full-content             Extract full page content (markdown)
  --max-snippets N           Max chunks per URL (1-10, default: 3)
  --min-score N              Min relevance score (0-1, default: 0.1)
  --include-domains d1,d2    Allow-list of domains (max 50)
  --exclude-domains d1,d2    Deny-list of domains (max 50)
  --raw                      Output raw response (no pretty-print)
  -h, --help                 Show this help message
EOF
  exit 0
}

# Parse arguments
QUERY=""
MARKET="en-us"
OFFSET=0
EXTRA_SNIPPETS="false"
FULL_CONTENT=""
MAX_SNIPPETS=3
MIN_SCORE=0.1
INCLUDE_DOMAINS=""
EXCLUDE_DOMAINS=""
RAW="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      ;;
    --extra-snippets)
      EXTRA_SNIPPETS="true"
      shift
      ;;
    --full-content)
      FULL_CONTENT="markdown"
      shift
      ;;
    --max-snippets)
      MAX_SNIPPETS="$2"
      shift 2
      ;;
    --min-score)
      MIN_SCORE="$2"
      shift 2
      ;;
    --include-domains)
      INCLUDE_DOMAINS="$2"
      shift 2
      ;;
    --exclude-domains)
      EXCLUDE_DOMAINS="$2"
      shift 2
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
      if [[ -z "$QUERY" ]]; then
        QUERY="$1"
      elif [[ "$MARKET" == "en-us" ]] && [[ "$1" =~ ^(en-us|fr-fr|de-de)$ ]]; then
        MARKET="$1"
      elif [[ "$OFFSET" -eq 0 ]] && [[ "$1" =~ ^[0-9]+$ ]]; then
        OFFSET="$1"
      else
        QUERY="$QUERY $1"
      fi
      shift
      ;;
  esac
done

if [[ -z "$QUERY" ]]; then
  echo "Error: query is required" >&2
  exit 1
fi

# Use python to build and execute the request
python3 - "$QUERY" "$MARKET" "$OFFSET" "$EXTRA_SNIPPETS" "$FULL_CONTENT" "$MAX_SNIPPETS" "$MIN_SCORE" "$INCLUDE_DOMAINS" "$EXCLUDE_DOMAINS" "$RAW" << 'PYEOF'
import json, sys, os, urllib.parse, subprocess

query = sys.argv[1]
market = sys.argv[2]
offset = int(sys.argv[3])
extra_snippets = sys.argv[4] == "true"
full_content = sys.argv[5] or None
max_snippets_arg = int(sys.argv[6])
min_score = float(sys.argv[7])
include_doms = sys.argv[8] or None
exclude_doms = sys.argv[9] or None
raw = sys.argv[10] == "true"
api_url = "https://api.staan.ai/v2/search/web"
api_key = os.environ["STAAN_API_KEY"]

if include_doms or exclude_doms or extra_snippets or full_content:
    body = {
        "q": query,
        "market": market,
        "offset": offset,
    }
    if include_doms:
        body["include_domains"] = [d.strip() for d in include_doms.split(",")]
    if exclude_doms:
        body["exclude_domains"] = [d.strip() for d in exclude_doms.split(",")]
    if extra_snippets:
        body["extra_snippets"] = True
        body["max_snippets"] = max_snippets_arg
        body["min_score"] = min_score
    if full_content:
        body["full_content"] = full_content
    body_json = json.dumps(body)
    cmd = [
        "curl", "--silent", "--max-time", "30",
        "-X", "POST",
        "-H", f"Authorization: Bearer {api_key}",
        "-H", "Content-Type: application/json",
        "-d", body_json,
    ]
else:
    params = urllib.parse.urlencode({
        "q": query, "market": market, "offset": offset
    })
    if extra_snippets:
        params += f"&extra_snippets=true&max_snippets={max_snippets_arg}&min_score={min_score}"
    if full_content:
        params += f"&full_content={full_content}"
    url = f"{api_url}?{params}"
    cmd = [
        "curl", "--silent", "--max-time", "30",
        "-G", url,
        "-H", f"Authorization: Bearer {api_key}",
    ]

proc = subprocess.run(cmd, capture_output=True, text=True)
result = proc.stdout.strip()
if raw:
    print(result)
else:
    try:
        print(json.dumps(json.loads(result), indent=2, ensure_ascii=False))
    except json.JSONDecodeError:
        print(f"API error: {result}", file=sys.stderr)
        sys.exit(1)
PYEOF
