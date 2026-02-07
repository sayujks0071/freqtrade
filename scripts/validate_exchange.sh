#!/bin/bash
set -e

# Source common environment setup
source scripts/common.sh

echo "Validating Delta Exchange setup..."
echo "Using API: $DELTA_BASE_URL"

# Check time drift (requires curl and date)
if command -v curl &> /dev/null && command -v date &> /dev/null; then
    echo "Checking time drift with $DELTA_BASE_URL..."
    # Use -I for HEAD request, grep Date header, cut value, remove carriage return
    SERVER_DATE=$(curl -sI "$DELTA_BASE_URL" | grep -i "^date:" | cut -d' ' -f2- | tr -d '\r')

    if [ ! -z "$SERVER_DATE" ]; then
        SERVER_TS=$(date -d "$SERVER_DATE" +%s)
        LOCAL_TS=$(date +%s)
        DIFF=$((LOCAL_TS - SERVER_TS))
        ABS_DIFF=${DIFF#-} # Absolute value

        if [ "$ABS_DIFF" -gt 30 ]; then
            echo "ERROR: Time drift is too high ($ABS_DIFF seconds). Please sync your clock (NTP)."
            exit 1
        fi
        echo "Time drift is acceptable ($ABS_DIFF seconds)."
    else
        echo "WARNING: Could not fetch server date. Skipping time drift check."
    fi
else
    echo "WARNING: curl or date not found. Skipping time drift check."
fi

# Run list-markets and capture output
TIMESTAMP=$(date +%s)
MARKETS_FILE="user_data/reports/markets_${TIMESTAMP}.json"

echo "Listing markets..."
# Ensure we have the image
docker compose pull freqtrade > /dev/null

# Run list-markets
# Redirect stderr to /dev/null to capture only stdout (JSON) if logs are on stderr
# Also using --print-json
docker compose run --rm freqtrade list-markets --exchange delta --trading-mode futures --print-json > "$MARKETS_FILE" 2>/dev/null

if [ ! -s "$MARKETS_FILE" ]; then
    echo "ERROR: Failed to fetch markets. Output file is empty."
    exit 1
fi

echo "Markets saved to $MARKETS_FILE"

# Validate whitelist
echo "Validating whitelist..."

# Python script to check whitelist and update if needed
if command -v python3 &> /dev/null; then
    python3 -c "
import json
import sys
import os

markets_file = '$MARKETS_FILE'
config_file = 'user_data/configs/${FREQTRADE_CONFIG_FILE:-config.delta.dryrun.json}'

try:
    with open(markets_file, 'r') as f:
        data = json.load(f)
        # Handle different potential structures
        if isinstance(data, list):
            markets = {m['symbol']: m for m in data}
        elif isinstance(data, dict):
            markets = data
        else:
            print('Unknown markets format')
            sys.exit(1)

    with open(config_file, 'r') as f:
        config = json.load(f)

    whitelist = config.get('exchange', {}).get('pair_whitelist', [])

    missing = []
    for pair in whitelist:
        if pair not in markets:
            missing.append(pair)

    if missing or not whitelist:
        if missing:
            print(f'Warning: The following pairs in whitelist are not found in markets: {missing}')
        if not whitelist:
            print('Warning: Whitelist is empty.')

        print('Generating new whitelist based on top volume pairs...')

        # Filter for USDT futures
        valid_markets = []
        for s, m in markets.items():
            # Check for USDT quote and linear (futures)
            # CCXT usually puts 'linear': True for futures
            # Or check symbol format BASE/QUOTE:SETTLE
            if '/USDT:USDT' in s:
                 valid_markets.append(m)

        # Sort by volume desc (quoteVolume usually available)
        # Use get just in case
        valid_markets.sort(key=lambda x: x.get('quoteVolume', 0) or 0, reverse=True)

        # Take top 20
        top_20 = [m['symbol'] for m in valid_markets[:20]]

        if top_20:
            config['exchange']['pair_whitelist'] = top_20
            with open(config_file, 'w') as f:
                json.dump(config, f, indent=4)
            print(f'Updated whitelist in {config_file} with top {len(top_20)} pairs: {top_20}')
        else:
            print('ERROR: No valid USDT futures pairs found in markets.')
            sys.exit(1)

    else:
        print('All whitelist pairs found in markets.')

except Exception as e:
    print(f'Error validating whitelist: {e}')
    sys.exit(1)
"
else
    echo "WARNING: python3 not found. Skipping whitelist validation."
fi

echo "Validation successful!"
