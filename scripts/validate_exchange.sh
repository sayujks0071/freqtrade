#!/bin/bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$DIR/common.sh"

echo "Validating Exchange Connection and Whitelist..."

TIMESTAMP=$(date -u +"%Y%m%d_%H%M%S")
REPORTS_DIR="/freqtrade/user_data/reports"
MARKETS_FILE="$REPORTS_DIR/markets_${TIMESTAMP}.json"

# Fetch Markets
echo "Fetching markets..."
docker compose run --rm \
    -e DELTA_ENV \
    -e DELTA_BASE_URL \
    freqtrade python3 /freqtrade/tools/fetch_markets.py \
    --output "$MARKETS_FILE"

if [ $? -ne 0 ]; then
    echo "Failed to fetch markets from Delta."
    exit 1
fi

echo "Markets fetched to user_data/reports/markets_${TIMESTAMP}.json"

# Validate Whitelist against Markets
# We can use a small python snippet or a tool.
# Let's use a python one-liner inside docker to access the files.

WHITELIST_FILE="/freqtrade/user_data/pairlists/whitelist.delta.json"

echo "Checking whitelist validity..."

docker compose run --rm freqtrade python3 -c "
import json
import sys
from pathlib import Path

try:
    with open('$MARKETS_FILE', 'r') as f:
        markets = json.load(f)

    market_map = {m['symbol']: m for m in markets if m.get('active')}

    whitelist_path = Path('$WHITELIST_FILE')
    if not whitelist_path.exists():
        print('Whitelist file not found. Skipping validation (first run?).')
        sys.exit(0)

    with whitelist_path.open('r') as f:
        wl_config = json.load(f)

    whitelist = wl_config.get('exchange', {}).get('pair_whitelist', [])

    missing = []
    inactive = []

    for pair in whitelist:
        if pair not in market_map:
            # Check if it exists but inactive
            found = False
            for m in markets:
                if m['symbol'] == pair:
                    inactive.append(pair)
                    found = True
                    break
            if not found:
                missing.append(pair)

    if missing:
        print(f'ERROR: Missing pairs in whitelist: {missing}')
    if inactive:
        print(f'ERROR: Inactive pairs in whitelist: {inactive}')

    if missing or inactive:
        sys.exit(1)

    print(f'SUCCESS: All {len(whitelist)} whitelist pairs are active.')

except Exception as e:
    print(f'Error validating whitelist: {e}')
    sys.exit(1)
"

if [ $? -eq 0 ]; then
    echo "Exchange validation passed."
else
    echo "Exchange validation failed."
    exit 1
fi
