#!/bin/bash
set -e
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
# Ensure we are in the root
cd "$(dirname "$0")/.."

source "$DIR/common.sh"

echo "Running Preflight Checks..."

# 1. Time Drift Check
echo "Checking Time Sync..."
# We use Python to compare local time with a reliable HTTP server (google.com)
python3 -c "
import urllib.request
import time
from datetime import datetime
import sys

try:
    req = urllib.request.Request('http://google.com', method='HEAD')
    with urllib.request.urlopen(req, timeout=5) as response:
        server_date_str = response.headers['Date']
        # Format: Fri, 12 Feb 2026 12:00:00 GMT
        try:
            server_time = datetime.strptime(server_date_str, '%a, %d %b %Y %H:%M:%S %Z')
        except ValueError:
             # Fallback for some servers if format differs slightly
             print(f'WARNING: Could not parse server date: {server_date_str}')
             sys.exit(0)

        # server_time is naive but in UTC (from GMT).
        # We need timestamp.
        # Python 3.11+ uses timezone-aware mostly, but let's be safe.
        # Assume GMT is UTC.
        import calendar
        server_ts = calendar.timegm(server_time.timetuple())

        local_ts = time.time()
        drift = abs(local_ts - server_ts)

        print(f'Server Time: {server_time} (UTC)')
        print(f'Local Time:  {datetime.utcfromtimestamp(local_ts)} (UTC)')
        print(f'Drift: {drift:.2f} seconds')

        if drift > 10:
            print('ERROR: System time drift is too high (> 10s). Please sync your clock using NTP.')
            sys.exit(1)

except Exception as e:
    print(f'WARNING: Could not check time sync: {e}')
    # We allow proceeding if network check fails, but warn.
    pass
"

if [ $? -ne 0 ]; then
    exit 1
fi

echo "Validating Exchange Connection..."

TIMESTAMP=$(date +%s)
REPORT_FILE="user_data/reports/markets_${TIMESTAMP}.json"
WHITELIST_FILE="user_data/configs/whitelist.json"

echo "Fetching markets from Delta ($DELTA_ENV)..."

# Ensure configs/whitelist.json exists
if [ ! -f "$WHITELIST_FILE" ]; then
    echo "{ \"exchange\": { \"pair_whitelist\": [] } }" > "$WHITELIST_FILE"
fi

# Run list-markets
docker compose run --rm freqtrade list-markets \
    --exchange delta \
    --trading-mode futures \
    --print-json > "${REPORT_FILE}.tmp"

# Robust JSON Parsing and Whitelist Validation
python3 -c "
import json
import sys
import os
import re

report_tmp = '${REPORT_FILE}.tmp'
report_file = '$REPORT_FILE'
whitelist_file = '$WHITELIST_FILE'

try:
    # Robustly read JSON from output (which might contain logs)
    with open(report_tmp, 'r') as f:
        content = f.read()

    # Find the JSON array part. Look for outermost [ ... ]
    # We try to find the first '[' and last ']'
    start = content.find('[')
    end = content.rfind(']')

    markets = None
    if start != -1 and end != -1:
        json_cand = content[start:end+1]
        try:
            markets = json.loads(json_cand)
        except json.JSONDecodeError:
            pass

    if markets is None:
        # Fallback to regex if simple slicing failed (e.g. nested structures)
        # But simple slicing usually works for a single list.
        print('ERROR: Could not find valid JSON list in output.')
        print('Raw Output Start:')
        print(content[:500])
        sys.exit(1)

    # Save clean JSON
    with open(report_file, 'w') as f:
        json.dump(markets, f, indent=4)

    print(f'Markets saved to {report_file}')
    print(f'Found {len(markets)} markets.')

    if not markets:
        print('ERROR: Market list is empty!')
        sys.exit(1)

    # Load whitelist
    if os.path.exists(whitelist_file):
        with open(whitelist_file, 'r') as f:
            wl_data = json.load(f)
            whitelist = wl_data.get('exchange', {}).get('pair_whitelist', [])
    else:
        whitelist = []

    # If whitelist is empty, generate a default one
    if not whitelist:
        print('Whitelist is empty. Generating default whitelist (top 5 USDT perps)...')
        candidates = [m for m in markets if '/USDT:USDT' in m]
        whitelist = candidates[:5]

        if not whitelist:
             print('WARNING: No USDT perps found!')
        else:
             print(f'Generated whitelist: {whitelist}')

        wl_data = {'exchange': {'pair_whitelist': whitelist}}
        with open(whitelist_file, 'w') as f:
            json.dump(wl_data, f, indent=4)

    # Validate whitelist
    missing = []
    for pair in whitelist:
        if pair not in markets:
            missing.append(pair)

    if missing:
        print(f'ERROR: The following whitelist pairs are NOT active or missing on Delta ({os.environ.get("DELTA_ENV")}):')
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
    rm "${REPORT_FILE}.tmp"
else
    echo "Validation Failed."
    rm "${REPORT_FILE}.tmp"
    exit 1
fi
