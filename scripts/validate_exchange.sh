#!/bin/bash
set -e
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$DIR/common.sh"

echo "Validating exchange connection and markets for $DELTA_ENV..."

TIMESTAMP=$(date -u +"%Y%m%d_%H%M%S")
REPORTS_DIR="user_data/reports"
MARKETS_FILE="$REPORTS_DIR/markets_validation_${TIMESTAMP}.json"

mkdir -p $REPORTS_DIR

echo "Fetching markets..."
TEMP_OUTPUT=$(mktemp)
docker compose run --rm freqtrade list-markets \
    --config /freqtrade/user_data/configs/config.delta.dryrun.json \
    --print-json > $TEMP_OUTPUT

if [ $? -ne 0 ]; then
    echo "Failed to fetch markets from Delta."
    rm $TEMP_OUTPUT
    exit 1
fi

mv $TEMP_OUTPUT $MARKETS_FILE

echo "Validating schema..."
python3 tools/validate_markets_schema.py "$MARKETS_FILE"

echo "Checking if whitelist pairs exist in the dump..."
CURRENT_WHITELIST="user_data/pairlists/whitelist.delta.json"
if [ -f "$CURRENT_WHITELIST" ]; then
    python3 -c "
import json, sys
try:
    whitelist_data = json.load(open('$CURRENT_WHITELIST'))
    # Handle list or object format for robustness
    if isinstance(whitelist_data, list):
        whitelist = whitelist_data
    else:
        whitelist = whitelist_data.get('exchange', {}).get('pair_whitelist', [])

    markets = json.load(open('$MARKETS_FILE'))
    market_symbols = {m['symbol'] for m in markets if m.get('active')}
    missing = [p for p in whitelist if p not in market_symbols]
    if missing:
        print(f'FAIL: Whitelist contains pairs not active in market dump: {missing}')
        sys.exit(1)
    print('PASS: All whitelist pairs are active.')
except Exception as e:
    print(f'Error validating whitelist: {e}')
    sys.exit(1)
"
else
    echo "No existing whitelist to validate."
fi

# Cleanup validation dump
rm $MARKETS_FILE

echo "Exchange validation successful."
