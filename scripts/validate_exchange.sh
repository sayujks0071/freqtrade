#!/bin/bash
set -e

# Change to repo root
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR/.."

source "$DIR/common.sh"

echo "=== Exchange Validation: Delta ($DELTA_ENV) ==="

# 1. Time Drift Check
echo "[1/4] Checking Time Drift..."
# Simple check using google.com date header vs local time
# We use python for this to avoid dependency issues with date formatting
python3 -c "
import sys, time
from urllib.request import urlopen
from datetime import datetime, timezone

try:
    # Use a reliable public server
    res = urlopen('http://google.com', timeout=5)
    date_str = res.headers['Date']
    # Parse date: Sat, 14 Feb 2026 11:25:00 GMT
    server_time = datetime.strptime(date_str, '%a, %d %b %Y %H:%M:%S %Z').replace(tzinfo=timezone.utc)
    local_time = datetime.now(timezone.utc)
    drift = abs((server_time - local_time).total_seconds())

    print(f'Server Time: {server_time}')
    print(f'Local Time:  {local_time}')
    print(f'Drift:       {drift:.2f} seconds')

    if drift > 10:
        print('ERROR: Time drift is too high (> 10s)! Please sync your clock (NTP).')
        sys.exit(1)
    print('Time Sync: OK')
except Exception as e:
    print(f'WARNING: Could not check time drift: {e}')
"

# 2. Check Exchange Availability (ccxt support)
echo "[2/4] Checking CCXT Delta Support..."
# We use a temp container to check exchanges
# We capture stderr too because freqtrade logs there
OUTPUT=$(docker compose run --rm freqtrade list-exchanges --print-one-column 2>&1)
if echo "$OUTPUT" | grep -q "^delta$"; then
    echo "Freqtrade supports 'delta': YES"
else
    echo "Freqtrade supports 'delta': NO"
    echo "Available exchanges (partial):"
    echo "$OUTPUT" | head -n 10
    exit 1
fi

# 3. Fetch Markets
echo "[3/4] Fetching Markets..."
REPORT_FILE="user_data/reports/markets_$(date +%s).json"
# We need to pass the config to ensure correct context
CONFIG_FILE="/freqtrade/user_data/configs/config.delta.dryrun.json"

# Ensure config exists for the container (it's mounted)
if [ ! -f "user_data/configs/config.delta.dryrun.json" ]; then
    echo "Config file not found: user_data/configs/config.delta.dryrun.json"
    exit 1
fi

docker compose run --rm freqtrade list-markets \
    --config "$CONFIG_FILE" \
    --exchange delta \
    --trading-mode futures \
    --print-json > "${REPORT_FILE}.tmp"

# Extract JSON array (lines starting with [)
grep -o '\[.*\]' "${REPORT_FILE}.tmp" > "$REPORT_FILE" || true

if [ ! -s "$REPORT_FILE" ]; then
    echo "Error: Failed to fetch markets or parse output."
    echo "Raw Output:"
    cat "${REPORT_FILE}.tmp"
    rm -f "$REPORT_FILE" "${REPORT_FILE}.tmp"
    exit 1
fi
rm "${REPORT_FILE}.tmp"
MARKET_COUNT=$(grep -o '"symbol":' "$REPORT_FILE" | wc -l)
echo "Markets fetched: $MARKET_COUNT saved to $REPORT_FILE"

if [ "$MARKET_COUNT" -lt "${MIN_MARKETS:-20}" ]; then
    echo "ERROR: Too few markets fetched ($MARKET_COUNT < ${MIN_MARKETS:-20})!"
    echo "Check connection or exchange status."
    exit 1
fi

# 4. Validate Whitelist
echo "[4/4] Validating Whitelist Configuration..."

python3 -c "
import json
import sys
import os

try:
    # Load Markets
    with open('$REPORT_FILE', 'r') as f:
        markets_data = json.load(f)
        if isinstance(markets_data, list) and len(markets_data) > 0 and isinstance(markets_data[0], dict):
             market_symbols = [m['symbol'] for m in markets_data]
        else:
             market_symbols = markets_data

    # Load Whitelist
    # Prioritize the standalone whitelist file if it exists
    whitelist_file = 'user_data/pairlists/whitelist.delta.json'
    whitelist = []

    if os.path.exists(whitelist_file):
        print(f'Loading whitelist from {whitelist_file}...')
        with open(whitelist_file, 'r') as f:
            wl_data = json.load(f)
            if 'exchange' in wl_data:
                whitelist = wl_data['exchange'].get('pair_whitelist', [])
            else:
                whitelist = wl_data
    else:
        # Fallback to main config
        config_file = 'user_data/configs/config.delta.dryrun.json'
        print(f'Loading whitelist from {config_file}...')
        with open(config_file, 'r') as f:
            config = json.load(f)
        whitelist = config.get('exchange', {}).get('pair_whitelist', [])

    print(f'Checking {len(whitelist)} pairs...')

    missing = []
    for pair in whitelist:
        if pair not in market_symbols:
            missing.append(pair)

    if missing:
        print(f'ERROR: The following whitelist pairs are NOT active on Delta ({os.environ.get("DELTA_ENV")}):')
        for m in missing:
            print(f' - {m}')
        sys.exit(1)

    print(f'SUCCESS: All whitelist pairs are valid.')

except Exception as e:
    print(f'Error validating: {e}')
    sys.exit(1)
"

if [ $? -eq 0 ]; then
    echo "=== Validation Successful ==="
else
    echo "=== Validation Failed ==="
    exit 1
fi
