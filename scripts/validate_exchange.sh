#!/bin/bash
set -e
cd "$(dirname "$0")/.."

# Source environment
source scripts/common.sh

echo "Validating Delta Exchange setup..."

# 1. Confirm 'delta' exchange availability
echo "Checking if 'delta' exchange is supported..."
if docker compose run --rm freqtrade list-exchanges | grep -q "delta"; then
    echo "SUCCESS: 'delta' exchange found."
else
    echo "ERROR: 'delta' exchange not found in Freqtrade installation."
    exit 1
fi

# 2. Fetch markets
TIMESTAMP=$(date -u +%Y%m%d_%H%M%S)
MARKETS_FILE="user_data/reports/markets_${TIMESTAMP}.json"

echo "Fetching markets for $DELTA_ENV to $MARKETS_FILE..."
# Ensure report directory exists
mkdir -p user_data/reports

# Run list-markets and capture output to file
# Using --print-json for structured output
# Redirect logs to file to keep stdout clean for JSON
docker compose run --rm freqtrade list-markets \
    --exchange delta \
    --trading-mode futures \
    --print-json \
    --logfile /freqtrade/user_data/logs/list_markets.log > "$MARKETS_FILE"

if [ ! -s "$MARKETS_FILE" ]; then
    echo "ERROR: Market dump is empty or failed."
    rm -f "$MARKETS_FILE"
    exit 1
fi

echo "Market dump saved to $MARKETS_FILE"

# 3. Validate whitelist pairs exist
WHITELIST_FILE="user_data/pairlists/whitelist.delta.${DELTA_ENV}.json"
if [ ! -f "$WHITELIST_FILE" ]; then
    echo "WARNING: Whitelist file $WHITELIST_FILE not found. Creating dummy..."
    echo '{"exchange": {"pair_whitelist": ["BTC/USDT:USDT"]}}' > "$WHITELIST_FILE"
fi

echo "Validating whitelist against market dump..."
python3 -c "
import json
import sys

whitelist_file = '$WHITELIST_FILE'
markets_file = '$MARKETS_FILE'

try:
    with open(whitelist_file, 'r') as f:
        wl_data = json.load(f)
        whitelist = set(wl_data.get('exchange', {}).get('pair_whitelist', []))

    with open(markets_file, 'r') as f:
        markets_data = json.load(f)
        # Handle list or dict format from freqtrade output
        if isinstance(markets_data, list):
             markets = {m['symbol'] for m in markets_data}
        elif 'markets' in markets_data:
             markets = {m['symbol'] for m in markets_data['markets']}
        else:
             # Depending on version, it might be dict of symbol->data
             markets = set(markets_data.keys())

    missing = whitelist - markets
    if missing:
        print(f'ERROR: The following pairs in whitelist are NOT in market dump: {missing}')
        sys.exit(1)

    print(f'SUCCESS: All {len(whitelist)} whitelisted pairs exist in market dump.')

except Exception as e:
    print(f'ERROR during validation: {e}')
    sys.exit(1)
"

# Clean up? No, keep the report.
echo "Validation complete."
