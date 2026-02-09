#!/bin/bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
# source "$DIR/common.sh" # if we had one

# Load environment
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

REPORT_FILE="user_data/reports/markets_check_$(date +%s).json"
CONFIG_FILE="/freqtrade/user_data/configs/config.delta.dryrun.json"

echo "Checking connectivity to Delta ($DELTA_ENV)..."

# Run list-markets
docker compose run --rm freqtrade list-markets \
    --config "$CONFIG_FILE" \
    --exchange delta \
    --trading-mode futures \
    --print-json > "${REPORT_FILE}.tmp"

if [ $? -ne 0 ]; then
    echo "ERROR: Failed to connect or fetch markets."
    rm "${REPORT_FILE}.tmp"
    exit 1
fi

# Extract JSON array
# Assuming clean output for now or simple grep
# Since we just want to validate connectivity, if list-markets succeeded, we are good.
# But let's check content.
mv "${REPORT_FILE}.tmp" "$REPORT_FILE"

echo "Connectivity OK. Markets saved to $REPORT_FILE"

echo "Validating Current Whitelist..."
WHITELIST_FILE="user_data/pairlists/whitelist.delta.json"

if [ ! -f "$WHITELIST_FILE" ]; then
    echo "WARN: Whitelist file not found at $WHITELIST_FILE. Please run update_markets_and_whitelist.sh first."
    exit 0
fi

# Python script to check whitelist validity against fetched markets
python3 -c "
import json
import sys

try:
    with open('$REPORT_FILE', 'r') as f:
        data = json.load(f)
        if isinstance(data, dict) and 'markets' in data:
            markets = set(m['symbol'] for m in data['markets'])
        else:
            markets = set(m['symbol'] for m in data if 'symbol' in m)

    with open('$WHITELIST_FILE', 'r') as f:
        wl_data = json.load(f)
        whitelist = wl_data.get('exchange', {}).get('pair_whitelist', [])

    missing = []
    for pair in whitelist:
        if pair not in markets:
            missing.append(pair)

    if missing:
        print(f'ERROR: The following whitelist pairs are MISSING from current market dump:')
        for m in missing:
            print(f' - {m}')
        sys.exit(1)

    print(f'SUCCESS: All {len(whitelist)} whitelist pairs are valid.')

except Exception as e:
    print(f'Error validating: {e}')
    sys.exit(1)
"

if [ $? -eq 0 ]; then
    echo "Validation Passed."
    rm "$REPORT_FILE"
else
    echo "Validation Failed."
    rm "$REPORT_FILE"
    exit 1
fi
