#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$DIR/common.sh"

echo "Validating Delta Exchange connection ($DELTA_ENV)..."

# Ensure we are in the root
cd "$(dirname "$0")/.."

TIMESTAMP=$(date -u +"%Y%m%d_%H%M%S")
MARKETS_FILE="user_data/reports/markets_${TIMESTAMP}.json"
mkdir -p user_data/reports

echo "1. Checking if 'delta' is supported..."
docker compose run --rm freqtrade list-exchanges | grep -i "delta" || echo "Delta might not be explicitly listed but CCXT supports it."

echo "2. Fetching markets to $MARKETS_FILE..."
# We use dryrun config to piggyback on credentials/settings
docker compose run --rm freqtrade list-markets \
    --config user_data/configs/config.delta.dryrun.json \
    --print-json > "$MARKETS_FILE"

if [ ! -s "$MARKETS_FILE" ]; then
    echo "FAIL: Markets file is empty."
    exit 1
fi

echo "3. Validating Schema..."
python3 tools/validate_markets_schema.py "$MARKETS_FILE"

echo "4. Checking current whitelist against fetched markets..."
WHITELIST_FILE="user_data/pairlists/whitelist.delta.json"
if [ -f "$WHITELIST_FILE" ]; then
    # We can use python to cross check
    python3 -c "
import json, sys
with open('$MARKETS_FILE') as f:
    markets = json.load(f)
    if isinstance(markets, dict) and 'markets' in markets: markets = markets['markets']
    market_pairs = {m['symbol'] for m in markets}

with open('$WHITELIST_FILE') as f:
    wl = json.load(f)
    pairs = wl.get('exchange', {}).get('pair_whitelist', [])

missing = [p for p in pairs if p not in market_pairs]
if missing:
    print(f'FAIL: Whitelist contains pairs not in market: {missing}')
    sys.exit(1)
else:
    print('PASS: All whitelist pairs exist on exchange.')
"
else
    echo "No whitelist found to validate."
fi

echo "Exchange validation complete."
