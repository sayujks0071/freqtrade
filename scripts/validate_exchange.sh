#!/bin/bash
set -e

# Similar to update_markets_and_whitelist.sh but simpler/focused on validation check
# and quick connectivity test.

DELTA_ENV=${DELTA_ENV:-india_testnet}
TIMESTAMP=$(date -u +"%Y%m%d_%H%M%S")
MARKETS_FILE="user_data/reports/markets_${TIMESTAMP}.json"
WHITELIST_FILE="user_data/pairlists/whitelist.delta.json"

echo "Validating Delta Exchange ($DELTA_ENV) connection..."

# 1. Fetch Markets Dump
if command -v docker >/dev/null 2>&1; then
  CMD="docker compose run --rm freqtrade list-markets --exchange delta --trading-mode futures --print-json"
else
  CMD="freqtrade list-markets --exchange delta --trading-mode futures --print-json"
fi

echo "Fetching markets..."
$CMD > "$MARKETS_FILE" 2>/dev/null

if ! jq empty "$MARKETS_FILE" >/dev/null 2>&1; then
  echo "Error: Fetched markets file is not valid JSON. Connectivity issue or bad output."
  # Try to cat the output to see error (it might be in the file if redirected)
  cat "$MARKETS_FILE"
  rm "$MARKETS_FILE"
  exit 1
fi

echo "Markets dumped to $MARKETS_FILE. Connection OK."

# 2. Validate Whitelist Pairs Exist
if [ -f "$WHITELIST_FILE" ]; then
    echo "Checking whitelist pairs against market dump..."
    # Python one-liner to check existence
    python3 -c "
import json, sys
try:
    with open('$MARKETS_FILE') as f: markets = json.load(f)
    with open('$WHITELIST_FILE') as f: whitelist = json.load(f)
    market_symbols = {m['symbol'] for m in markets}
    whitelist_set = set(whitelist)
    missing = whitelist_set - market_symbols
    if missing:
        print(f'Missing pairs in market dump: {missing}')
        sys.exit(1)
    else:
        print('All whitelist pairs exist in market dump.')
except Exception as e:
    print(f'Error: {e}')
    sys.exit(1)
"
else
    echo "No whitelist file found at $WHITELIST_FILE. Skipping check."
fi

echo "Exchange validation passed."
