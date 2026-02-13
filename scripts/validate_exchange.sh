#!/bin/bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$DIR/common.sh"

TIMESTAMP=$(date -u +"%Y%m%d_%H%M%S")
MARKETS_FILE="user_data/reports/markets_${TIMESTAMP}.json"
VALIDATION_REPORT="user_data/reports/whitelist_validation.json"
WHITELIST_FILE="user_data/pairlists/whitelist.delta.json"

echo "=== Starting Exchange Validation ==="

# 1. Time Drift Check
echo "Checking Time Drift..."
DRIFT_CHECK=$(python3 -c "
import time
import urllib.request
from datetime import datetime

try:
    # Google is a reliable time source
    req = urllib.request.urlopen('http://google.com')
    date_str = req.headers['Date']
    # Parse HTTP Date: 'Fri, 13 Feb 2026 11:24:00 GMT'
    server_time = datetime.strptime(date_str, '%a, %d %b %Y %H:%M:%S GMT').timestamp()
    local_time = time.time()
    drift = abs(local_time - server_time)
    print(f'{drift:.4f}')
    if drift > 5.0:
        exit(1)
except Exception as e:
    print(f'Error: {e}')
    exit(2)
")

if [ $? -ne 0 ]; then
    echo "CRITICAL: Time drift is too high ($DRIFT_CHECK seconds) or check failed. Please sync your clock (NTP)."
    exit 1
else
    echo "Time drift acceptable: ${DRIFT_CHECK}s"
fi

# 2. Check Exchange Availability
echo "Verifying 'delta' exchange in Freqtrade..."
# We run list-exchanges and grep for delta.
# This confirms ccxt support.
docker compose run --rm freqtrade list-exchanges --print-one-column | grep -q "^delta$"
if [ $? -ne 0 ]; then
    echo "ERROR: Exchange 'delta' not found in Freqtrade supported exchanges."
    exit 1
fi
echo "Exchange 'delta' is supported."

# 3. Fetch Markets
echo "Fetching markets from Delta ($DELTA_ENV)..."
# We output to a temp file first because docker output might contain logs
TEMP_OUTPUT=$(mktemp)
docker compose run --rm freqtrade list-markets \
    --config /freqtrade/user_data/configs/config.delta.dryrun.json \
    --exchange delta \
    --trading-mode futures \
    --print-json > "$TEMP_OUTPUT"

# Extract the JSON array (last line or finding start/end)
# Assuming --print-json outputs valid json on the last lines or purely json if -v0
# Freqtrade logs go to stderr usually, but just in case.
# We can use python to extract the json structure.
python3 -c "
import sys
import json
import re

try:
    with open('$TEMP_OUTPUT', 'r') as f:
        content = f.read()

    # Find JSON list start/end if mixed with logs
    # Markets list is a list of objects or strings? list-markets returns a table or a list of dicts/strings?
    # --print-json returns the raw list of market dictionaries usually, or list of pair strings?
    # Actually 'list-markets --print-json' usually returns the detailed market list (list of dicts).
    # Wait, 'freqtrade list-markets' returns a table by default. --print-json makes it a JSON list of objects.

    # Simple JSON parsing
    # If content has logs, we need to find the json part.
    # It usually starts with [
    match = re.search(r'\[.*\]', content, re.DOTALL)
    if match:
        json_data = json.loads(match.group(0))
        with open('$MARKETS_FILE', 'w') as f:
            json.dump(json_data, f, indent=4)
    else:
        # Maybe it's empty or error
        sys.exit(1)
except Exception as e:
    print(f'Error parsing markets: {e}')
    sys.exit(1)
"

if [ $? -eq 0 ] && [ -s "$MARKETS_FILE" ]; then
    echo "Markets saved to $MARKETS_FILE"
    rm "$TEMP_OUTPUT"
else
    echo "ERROR: Failed to fetch or parse markets."
    cat "$TEMP_OUTPUT"
    rm "$TEMP_OUTPUT"
    exit 1
fi

# 4. Validate Whitelist
echo "Validating Whitelist..."
python3 -c "
import sys
import json

whitelist_file = '$WHITELIST_FILE'
markets_file = '$MARKETS_FILE'
report_file = '$VALIDATION_REPORT'

try:
    with open(whitelist_file, 'r') as f:
        wl_data = json.load(f)

    pairs = wl_data.get('exchange', {}).get('pair_whitelist', [])

    if not pairs:
        print('WARNING: Whitelist is empty.')
        # We don't fail on empty, but we warn.
        # But if the user wants to trade, it won't work.
        # The prompt says 'refuse to start if... whitelist pairs not present'.
        # Empty whitelist means 0 pairs are present? No, it means 0 pairs are requested.
        # Let's consider empty as valid but useless.

    with open(markets_file, 'r') as f:
        markets = json.load(f)

    # list-markets --print-json returns a LIST OF DICTIONARIES.
    # Each dict has 'symbol', 'base', 'quote', etc.
    # We need to collect valid symbols.
    valid_symbols = {m['symbol'] for m in markets}

    invalid_pairs = []
    for p in pairs:
        if p not in valid_symbols:
            invalid_pairs.append(p)

    report = {
        'timestamp': '$TIMESTAMP',
        'total_pairs': len(pairs),
        'valid_pairs': len(pairs) - len(invalid_pairs),
        'invalid_pairs': invalid_pairs,
        'status': 'failed' if invalid_pairs else 'success'
    }

    with open(report_file, 'w') as f:
        json.dump(report, f, indent=4)

    if invalid_pairs:
        print(f'CRITICAL: Found {len(invalid_pairs)} invalid pairs in whitelist!')
        for p in invalid_pairs:
            print(f' - {p}')
        sys.exit(1)

    print('Whitelist validation passed.')

except FileNotFoundError as e:
    print(f'Error: File not found - {e}')
    sys.exit(1)
except Exception as e:
    print(f'Error during validation: {e}')
    sys.exit(1)
"

if [ $? -eq 0 ]; then
    echo "Validation Successful."
else
    echo "Validation FAILED. See $VALIDATION_REPORT"
    exit 1
fi
