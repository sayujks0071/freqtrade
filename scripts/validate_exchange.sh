#!/bin/bash
set -e

# Source common env and functions
source "$(dirname "$0")/common.sh"

echo "Validating Exchange Connection and Markets for $DELTA_ENV..."
echo "Base URL: $BASE_URL"

# 1. Time Drift Check
check_time_drift

# 2. Verify Exchange Availability
echo "Verifying 'delta' exchange availability..."
# Check if delta is in the list of exchanges supported by the ccxt version in the container
docker compose run --rm freqtrade list-exchanges --one-column | grep -q "^delta$"
if [ $? -ne 0 ]; then
    echo "Error: Exchange 'delta' not found in available exchanges."
    exit 1
fi
echo "Exchange 'delta' confirmed available."

# 3. Fetch Markets
REPORT_FILE="user_data/reports/markets_$(date +%Y%m%d_%H%M%S).json"
LATEST_LINK="user_data/reports/markets_latest.json"

echo "Fetching markets to $REPORT_FILE..."

# We run list-markets inside the container to ensure we use the same CCXT version and config
# We map the env vars for URL overrides
docker compose run --rm \
    -e FREQTRADE__EXCHANGE__CCXT_CONFIG__URLS__API__public="$FREQTRADE__EXCHANGE__CCXT_CONFIG__URLS__API__public" \
    -e FREQTRADE__EXCHANGE__CCXT_CONFIG__URLS__API__private="$FREQTRADE__EXCHANGE__CCXT_CONFIG__URLS__API__private" \
    freqtrade list-markets \
    --exchange delta \
    --trading-mode futures \
    --print-json > "$REPORT_FILE"

# Check if file is valid JSON (simple check)
if [ ! -s "$REPORT_FILE" ]; then
    echo "Error: Market dump is empty."
    exit 1
fi

# Create/Update symlink
ln -sf "$(basename "$REPORT_FILE")" "$LATEST_LINK"

# 3. Validate Markets Schema & Whitelist
echo "Validating market data..."

# Run python validation script inside container (has python and dependencies)
# We map ./tools to /freqtrade/tools in docker-compose
docker compose run --rm --entrypoint python3 \
    freqtrade \
    /freqtrade/tools/validate_markets_schema.py "/freqtrade/$REPORT_FILE"

# 4. Update Whitelist (Optional/Guided)
# The user requirement says "whitelist must be generated ... or user selects".
# For now, we just validate. The validate_markets_schema.py could be enhanced to generate it,
# or we can use a separate step.
# Let's check if the current whitelist pairs exist in the dump.
# We can use a simple python oneliner or script for this check.

echo "Verifying configured whitelist against market dump..."
WHITELIST_FILE="user_data/pairlists/whitelist.delta.json"

if [ -f "$WHITELIST_FILE" ]; then
    docker compose run --rm --entrypoint python3 \
        freqtrade \
        -c "
import json
import sys

try:
    with open('/freqtrade/$REPORT_FILE') as f:
        markets = json.load(f)
        # Handle dict response
        if isinstance(markets, dict) and 'markets' in markets: markets = markets['markets']
        market_symbols = {m['symbol'] for m in markets}

    with open('/freqtrade/$WHITELIST_FILE') as f:
        wl = json.load(f)
        # Strict check for exchange.pair_whitelist
        if 'exchange' not in wl or 'pair_whitelist' not in wl['exchange']:
             print('ERROR: Whitelist file has incorrect format. Must contain {\"exchange\": {\"pair_whitelist\": [...]}}')
             sys.exit(1)

        pairs = wl['exchange']['pair_whitelist']

    missing = [p for p in pairs if p not in market_symbols]
    if missing:
        print(f'ERROR: The following whitelist pairs are not in market dump: {missing}')
        sys.exit(1)
    else:
        print(f'SUCCESS: All {len(pairs)} whitelist pairs are valid.')

except Exception as e:
    print(f'Error checking whitelist: {e}')
    sys.exit(1)
"
else
    echo "Warning: Whitelist file $WHITELIST_FILE not found."
fi

echo "Validation Complete. System ready."
