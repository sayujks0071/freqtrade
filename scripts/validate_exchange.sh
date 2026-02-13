#!/bin/bash
set -e
cd "$(dirname "$0")/.."

# Load .env if exists
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

echo "Validating exchange connection..."
TEMP_OUTPUT=$(mktemp)

# Fetch markets
docker compose run --rm -T freqtrade list-markets \
    --config /freqtrade/user_data/configs/config.delta.dryrun.json \
    --print-json > $TEMP_OUTPUT

if [ $? -ne 0 ]; then
    echo "FAIL: Could not connect or fetch markets."
    rm $TEMP_OUTPUT
    exit 1
fi

echo "PASS: Connected and fetched markets."

# Validate schema
if ! python3 tools/validate_markets_schema.py "$TEMP_OUTPUT"; then
    echo "FAIL: Market schema validation failed."
    rm $TEMP_OUTPUT
    exit 1
fi

echo "PASS: Market schema valid."

# Validate whitelist coverage
WHITELIST_JSON="user_data/pairlists/whitelist.delta.json"
if [ -f "$WHITELIST_JSON" ]; then
    echo "Validating whitelist coverage..."
    python3 -c "
import json, sys
try:
    with open('$WHITELIST_JSON') as f:
        wl = json.load(f).get('exchange', {}).get('pair_whitelist', [])
    with open('$TEMP_OUTPUT') as f:
        mkts = json.load(f)
        if isinstance(mkts, dict) and 'markets' in mkts: mkts = mkts['markets']
        mkt_syms = {m['symbol'] for m in mkts}

    missing = [p for p in wl if p not in mkt_syms]
    if missing:
        print(f'FAIL: Whitelist contains pairs not in exchange: {missing}')
        sys.exit(1)
    else:
        print(f'PASS: All {len(wl)} whitelist pairs exist on exchange.')
except Exception as e:
    print(f'ERROR: {e}')
    sys.exit(1)
"
else
    echo "WARN: No whitelist found at $WHITELIST_JSON to validate."
fi

rm $TEMP_OUTPUT
echo "Exchange validation complete."
