#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$DIR/common.sh"

echo "Validating Exchange Connection..."

# 1. Check availability
echo "Checking 'delta' exchange availability..."
if docker compose run --rm freqtrade list-exchanges --one-column | grep -q "^delta$"; then
    echo "PASS: Delta exchange found."
else
    echo "FAIL: Delta exchange not found in list-exchanges."
    exit 1
fi

# 2. List markets and save
TIMESTAMP=$(date +%s)
REPORT_FILE="user_data/reports/markets_${TIMESTAMP}.json"
mkdir -p user_data/reports

echo "Fetching markets..."
docker compose run --rm freqtrade list-markets \
    --config /freqtrade/user_data/configs/config.delta.dryrun.json \
    --exchange delta \
    --trading-mode futures \
    --print-json > "$REPORT_FILE"

if [ ! -s "$REPORT_FILE" ]; then
    echo "FAIL: Market dump is empty."
    exit 1
fi
echo "Markets saved to $REPORT_FILE"

# 3. Validate Whitelist
WHITELIST_FILE="user_data/pairlists/whitelist.delta.json"
if [ ! -f "$WHITELIST_FILE" ]; then
    echo "WARN: Whitelist file not found. Generating defaults..."
    python3 tools/generate_whitelist.py "$REPORT_FILE" > "$WHITELIST_FILE"
fi

echo "Validating whitelist pairs..."
python3 -c "
import json, sys
try:
    with open('$REPORT_FILE') as f:
        data = json.load(f)
    markets = data if isinstance(data, list) else data.get('markets', [])
    symbols = {m['symbol'] for m in markets if 'symbol' in m}

    with open('$WHITELIST_FILE') as f:
        wl = json.load(f).get('exchange', {}).get('pair_whitelist', [])

    missing = [p for p in wl if p not in symbols]
    if missing:
        print(f'FAIL: Pairs in whitelist but not in market dump: {missing}')
        sys.exit(1)
    print(f'PASS: All {len(wl)} pairs are valid.')
except Exception as e:
    print(f'Error: {e}')
    sys.exit(1)
"
