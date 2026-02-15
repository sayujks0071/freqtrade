#!/bin/bash
set -e

# Get the directory of the script
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$DIR/common.sh"

echo "=== Starting Exchange Validation for $DELTA_ENV ==="

# 1. Time Sync Check
echo "Checking time synchronization..."
python3 - <<EOF
import time
import sys
from datetime import datetime, timezone
import urllib.request

try:
    print(f'System Time (UTC): {datetime.now(timezone.utc)}')

    # Check against Google for rough drift check
    try:
        # Set timeout to avoid hanging
        with urllib.request.urlopen('http://google.com', timeout=5) as response:
            if 'Date' in response.headers:
                server_date = response.headers['Date']
                # parse: Fri, 15 Feb 2026 11:20:00 GMT
                # Use email.utils.parsedate_to_datetime or simple strptime
                # Trying simple strptime first, assuming standard format
                server_time = datetime.strptime(server_date, '%a, %d %b %Y %H:%M:%S %Z').replace(tzinfo=timezone.utc)
                local_time = datetime.now(timezone.utc)
                drift = abs((local_time - server_time).total_seconds())

                print(f'Google Time (UTC): {server_time}')
                print(f'Time Drift: {drift:.2f} seconds')

                if drift > 30:
                    print('ERROR: Time drift is too high (>30s). Please enable NTP.')
                    sys.exit(1)
            else:
                print('WARNING: Could not fetch Date header from Google.')
    except Exception as e:
        print(f'WARNING: Could not check time against Google: {e}')

except Exception as e:
    print(f'Error in time check: {e}')
    sys.exit(1)
EOF

# 2. Check Exchange Availability
echo "Checking if 'delta' exchange is supported by ccxt..."
# We assume ccxt is installed in the environment where we run this script?
# No, we run this script on the host. The host might not have ccxt.
# The previous version used python3 -c "import ccxt". If the user doesn't have ccxt installed on host, this fails.
# We should probably run this check inside the container or assume the host has minimal python.
# Since the prompt says "DevOps engineer", running validation inside docker is safer.
# BUT, we want to check if the *host* time is synced, which we did.
# For ccxt availability, we can assume Freqtrade image has it.
# So `freqtrade list-exchanges` is better.
# But running docker for just that is slow.
# Let's skip the python ccxt check on host and rely on `freqtrade list-exchanges` inside docker if we really want.
# Actually, let's just use `docker compose run ... list-exchanges` to be sure.

echo "Verifying Delta exchange via Freqtrade..."
docker compose run --rm freqtrade list-exchanges --print-one-column > exchange_list.tmp
if grep -q "^delta$" exchange_list.tmp; then
    echo "SUCCESS: Delta exchange found."
else
    echo "ERROR: Delta exchange not found in Freqtrade image."
    cat exchange_list.tmp
    rm exchange_list.tmp
    exit 1
fi
rm exchange_list.tmp

# 3. Fetch Markets
TIMESTAMP=$(date -u +"%Y%m%d_%H%M%S")
REPORT_FILE="user_data/reports/markets_${TIMESTAMP}.json"
echo "Fetching markets to $REPORT_FILE..."

# Capture output
docker compose run --rm freqtrade list-markets \
    --config /freqtrade/user_data/configs/config.delta.dryrun.json \
    --exchange delta \
    --trading-mode futures \
    --print-json > "${REPORT_FILE}.tmp"

if [ $? -ne 0 ]; then
    echo "ERROR: Failed to fetch markets."
    rm "${REPORT_FILE}.tmp"
    exit 1
fi

# Clean and Save JSON
python3 - "$REPORT_FILE" "${REPORT_FILE}.tmp" <<'EOF'
import sys
import json
import re

target_file = sys.argv[1]
source_file = sys.argv[2]

try:
    with open(source_file, 'r') as f:
        content = f.read()

    # Find the JSON list bracket
    # Freqtrade output might be just the list if --print-json is clean
    # But usually it has log prefixes.
    match = re.search(r'\[.*\]', content, re.DOTALL)
    if match:
        json_str = match.group(0)
        # Parse to ensure validity
        data = json.loads(json_str)

        with open(target_file, 'w') as f:
            json.dump(data, f, indent=4)
        print(f'SUCCESS: Fetched {len(data)} markets.')
    else:
        # Maybe it is already clean JSON?
        try:
            data = json.loads(content)
            if isinstance(data, list):
                with open(target_file, 'w') as f:
                    json.dump(data, f, indent=4)
                print(f'SUCCESS: Fetched {len(data)} markets (clean).')
            else:
                raise ValueError("Not a list")
        except:
            print('ERROR: Could not find JSON list in output.')
            print('Raw output start:', content[:200])
            sys.exit(1)
except Exception as e:
    print(f'ERROR processing markets dump: {e}')
    sys.exit(1)
EOF
rm "${REPORT_FILE}.tmp"

# 4. Generate Whitelist
WHITELIST_FILE="user_data/pairlists/whitelist.delta.json"
echo "Generating whitelist from markets to $WHITELIST_FILE..."

python3 - "$REPORT_FILE" "$WHITELIST_FILE" <<'EOF'
import sys
import json

report_file = sys.argv[1]
whitelist_file = sys.argv[2]

try:
    with open(report_file, 'r') as f:
        markets = json.load(f)

    whitelist = []

    for m in markets:
        # Handle dict or string
        pair = m['symbol'] if isinstance(m, dict) else m

        # Filter for USDT futures
        # We look for pairs ending in :USDT (linear) or standard formats
        # Adjust logic as per Delta's symbols in CCXT
        if '/USDT:USDT' in pair:
            whitelist.append(pair)

    whitelist = sorted(list(set(whitelist)))

    if not whitelist:
        print('WARNING: No futures pairs found in market dump! Whitelist will be empty.')
    else:
        print(f'Found {len(whitelist)} futures pairs.')

    output = {
        "exchange": {
            "pair_whitelist": whitelist
        },
        "pairlists": [
            {"method": "StaticPairList"}
        ]
    }

    with open(whitelist_file, 'w') as f:
        json.dump(output, f, indent=4)

except Exception as e:
    print(f'ERROR generating whitelist: {e}')
    sys.exit(1)
EOF

# 5. Validate Whitelist against Dump
echo "Validating generated whitelist..."
python3 - "$WHITELIST_FILE" "$REPORT_FILE" <<'EOF'
import sys
import json

whitelist_file = sys.argv[1]
report_file = sys.argv[2]

try:
    with open(whitelist_file, 'r') as f:
        config = json.load(f)
        whitelist = config.get('exchange', {}).get('pair_whitelist', [])

    with open(report_file, 'r') as f:
        raw = json.load(f)
        market_pairs = set()
        for m in raw:
            market_pairs.add(m['symbol'] if isinstance(m, dict) else m)

    missing = []
    for p in whitelist:
        if p not in market_pairs:
            missing.append(p)

    if missing:
        print(f'ERROR: The following pairs in whitelist are not in market dump: {missing}')
        sys.exit(1)

    print('SUCCESS: All whitelist pairs exist in market dump.')

except Exception as e:
    print(f'ERROR validating whitelist: {e}')
    sys.exit(1)
EOF

echo "=== Validation Complete ==="
