#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$DIR/common.sh"

echo "=== VALIDATING EXCHANGE CONNECTION ==="

# 1. Check if 'delta' exchange is supported
echo "Checking for 'delta' exchange in ccxt..."
if docker compose run --rm freqtrade list-exchanges --one-column | grep -q "^delta$"; then
    echo "PASS: Exchange 'delta' found."
else
    echo "FAIL: Exchange 'delta' NOT found in Freqtrade/CCXT."
    exit 1
fi

# 2. Check Time Drift
echo "Checking Time Drift..."
docker compose run --rm freqtrade python3 -c "
import ccxt
import time
import sys
import os

try:
    exchange = ccxt.delta()
    # Inject URL from env if set (propagated via docker-compose)
    base_url = os.environ.get('FREQTRADE__EXCHANGE__CCXT_CONFIG__URLS__API__public')
    if base_url:
        print(f'Using Base URL: {base_url}')
        exchange.urls['api']['public'] = base_url
        exchange.urls['api']['private'] = base_url

    # timeout
    exchange.timeout = 5000

    start = time.time()
    server_time = exchange.fetch_time()
    end = time.time()

    # Adjust for latency (rtt/2)
    latency = (end - start) * 1000 / 2
    local_time = int(time.time() * 1000)

    diff = abs(server_time - local_time)

    print(f'Server Time: {server_time}')
    print(f'Local Time:  {local_time}')
    print(f'Drift:       {diff:.2f} ms (Latency: {latency:.2f} ms)')

    if diff > 5000:
        print('FAIL: Time drift > 5000ms. Please sync your system clock (NTP).')
        sys.exit(1)
    else:
        print('PASS: Time sync OK')

except Exception as e:
    print(f'Error fetching time: {e}')
    # Fail if we can't verify time
    sys.exit(1)
"

if [ $? -ne 0 ]; then
    echo "FAIL: Time Drift Check Failed."
    exit 1
fi

# 3. Fetch Markets & Validate Whitelist
echo "Fetching Markets and Validating Whitelist..."
"$DIR/update_markets_and_whitelist.sh"

if [ $? -ne 0 ]; then
    echo "FAIL: Market validation failed."
    exit 1
fi

echo "=== VALIDATION SUCCESS ==="
