#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$DIR/common.sh"

echo "=========================================="
echo "Delta Exchange Validator ($DELTA_ENV)"
echo "=========================================="

echo "[1/4] Checking Exchange Availability..."
if docker compose run --rm freqtrade list-exchanges | grep -q "delta"; then
    echo "SUCCESS: Exchange 'delta' is present."
else
    echo "ERROR: Exchange 'delta' is NOT supported by the current Freqtrade image."
    exit 1
fi

echo "[2/4] Checking Time Drift..."
# Check drift using CCXT inside the container
docker compose run --rm freqtrade python3 -c "
import ccxt
import time
import sys
import os

try:
    # Initialize Delta
    exchange = ccxt.delta()

    # Override URL if set in environment (passed via docker-compose)
    base_url = os.environ.get('FREQTRADE__EXCHANGE__CCXT_CONFIG__URLS__API__public')
    if base_url:
        exchange.urls['api']['public'] = base_url
        exchange.urls['api']['private'] = base_url

    # Fetch time
    server_time = exchange.fetch_time()
    system_time = int(time.time() * 1000)
    drift = abs(server_time - system_time)

    print(f'Server Time: {server_time}')
    print(f'System Time: {system_time}')
    print(f'Drift: {drift} ms')

    if drift > 5000:
        print('ERROR: Time drift is too high (>5000ms). Please sync your clock (NTP).')
        sys.exit(1)
    else:
        print('SUCCESS: Time drift is within acceptable limits.')

except Exception as e:
    print(f'Time check failed: {e}')
    sys.exit(1)
"

if [ $? -ne 0 ]; then
    echo "Time Sync Check Failed!"
    exit 1
fi

echo "[3/4] Fetching Markets..."
REPORT_FILE="user_data/reports/markets_$(date +%s).json"
CONFIG_FILE="user_data/configs/config.delta.dryrun.json"

docker compose run --rm freqtrade list-markets \
    --config /freqtrade/user_data/configs/config.delta.dryrun.json \
    --exchange delta \
    --trading-mode futures \
    --print-json > "${REPORT_FILE}.tmp"

# Extract JSON
python3 -c "
import sys
import json
import re

input_file = '${REPORT_FILE}.tmp'
output_file = '$REPORT_FILE'

try:
    with open(input_file, 'r') as f:
        content = f.read()

    match = re.search(r'\[.*\]', content, re.DOTALL)
    if not match:
        print('Error: Could not find JSON output in command result.')
        sys.exit(1)

    json_str = match.group(0)
    data = json.loads(json_str)

    with open(output_file, 'w') as f:
        json.dump(data, f, indent=2)

    print(f'Markets saved to {output_file}')
except Exception as e:
    print(f'Error parsing markets: {e}')
    sys.exit(1)
"

rm "${REPORT_FILE}.tmp"

echo "[4/4] Validating Whitelist..."
python3 -c "
import sys
import json

report_file = '$REPORT_FILE'
config_file = '$CONFIG_FILE'

try:
    with open(report_file, 'r') as f:
        markets = json.load(f)

    if markets and isinstance(markets[0], dict):
        active_pairs = {m['symbol'] for m in markets}
    else:
        active_pairs = set(markets)

    with open(config_file, 'r') as f:
        config = json.load(f)

    whitelist = config.get('exchange', {}).get('pair_whitelist', [])

    print(f'Checking {len(whitelist)} configured pairs against {len(active_pairs)} active markets...')

    missing = [p for p in whitelist if p not in active_pairs]

    if missing:
        print('ERROR: The following pairs in whitelist are invalid or inactive:')
        for p in missing:
            print(f'  - {p}')
        sys.exit(1)

    print('SUCCESS: All whitelist pairs are valid.')

except Exception as e:
    print(f'Validation failed: {e}')
    sys.exit(1)
"

if [ $? -eq 0 ]; then
    echo "=========================================="
    echo "VALIDATION PASSED"
    echo "=========================================="
    exit 0
else
    echo "=========================================="
    echo "VALIDATION FAILED"
    echo "=========================================="
    exit 1
fi
