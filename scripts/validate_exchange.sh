#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$DIR/common.sh"

REPORT_FILE="user_data/reports/markets_$(date +%s).json"
# We check the default dryrun config + whitelist
# Note: These paths are inside the container
CONFIG_FILES="--config /freqtrade/user_data/configs/config.delta.dryrun.json --config /freqtrade/user_data/pairlists/whitelist.delta.json"

echo "=== Delta Exchange Validation / Preflight ==="
echo "Mode: $DELTA_ENV ($BASE_URL)"

# 0. Time Check
echo "0. System Time Check..."
echo "System UTC Time: $(date -u)"
if command -v timedatectl &> /dev/null; then
    if timedatectl status | grep -q "System clock synchronized: yes"; then
         echo "PASS: System clock is synchronized."
    else
         echo "WARNING: System clock might not be synchronized! Check NTP."
         # We warn but don't fail unless strict
    fi
else
    echo "WARNING: 'timedatectl' not found. Ensure your system clock is accurate to avoid API errors."
fi

# 1. Check Exchange Availability (using list-exchanges)
echo "1. Checking CCXT Exchange Availability..."
if ! docker compose run --rm freqtrade list-exchanges --print-one-column | grep -q "delta"; then
    echo "FAIL: 'delta' exchange not found in Freqtrade image!"
    exit 1
fi
echo "PASS: 'delta' exchange is supported."

# 2. Fetch Markets
echo "2. Fetching Futures Markets..."
# We use the config to ensure credentials/URLs are used
if ! docker compose run --rm freqtrade list-markets \
    $CONFIG_FILES \
    --exchange delta \
    --trading-mode futures \
    --print-json > "${REPORT_FILE}.tmp" 2>/dev/null; then
    echo "FAIL: Error running list-markets command."
    rm -f "${REPORT_FILE}.tmp"
    exit 1
fi

# Extract JSON content
# Handles potential log output before the JSON
grep -o '\[.*\]' "${REPORT_FILE}.tmp" > "$REPORT_FILE" || true

if [ ! -s "$REPORT_FILE" ]; then
    cat "${REPORT_FILE}.tmp"
    echo "FAIL: Could not fetch markets. Check your API keys and connection."
    rm -f "${REPORT_FILE}.tmp"
    exit 1
fi
rm "${REPORT_FILE}.tmp"
echo "PASS: Markets saved to $REPORT_FILE"

# 3. Validate Whitelist
echo "3. Validating Whitelist Pairs..."

# Python script to cross-reference whitelist with market dump
python3 -c "
import json
import sys

try:
    with open('$REPORT_FILE', 'r') as f:
        markets = json.load(f)
        # Handle list of dicts (full info) or list of strings (simple list)
        if markets and len(markets) > 0:
            if isinstance(markets[0], dict):
                market_symbols = {m['symbol'] for m in markets}
            else:
                market_symbols = set(markets)
        else:
            market_symbols = set()

    with open('user_data/pairlists/whitelist.delta.json', 'r') as f:
        whitelist_data = json.load(f)
        whitelist = whitelist_data.get('exchange', {}).get('pair_whitelist', [])

    if not whitelist:
        print('WARNING: Whitelist is empty!')
        sys.exit(0)

    missing = []
    for pair in whitelist:
        if pair not in market_symbols:
            missing.append(pair)

    if missing:
        print(f'FAIL: The following whitelist pairs are NOT active on Delta ({sys.argv[1]}):')
        for m in missing:
            print(f' - {m}')
        sys.exit(1)

    print(f'PASS: All {len(whitelist)} whitelist pairs are valid.')

except Exception as e:
    print(f'Error validating: {e}')
    sys.exit(1)
" "$DELTA_ENV"

if [ $? -ne 0 ]; then
    echo "Validation Failed!"
    exit 1
fi

echo "=== Validation Complete: SUCCESS ==="
