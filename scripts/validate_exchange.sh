#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$DIR/common.sh"

echo "Validating Exchange Connection and Markets..."

REPORT_FILE="user_data/reports/markets_$(date +%s).json"

# Ensure report dir exists
mkdir -p user_data/reports

echo "Fetching markets..."
# We use config.delta.dryrun.json which relies on env vars for keys.
# common.sh exports them.
docker compose run --rm freqtrade list-markets \
    --config /freqtrade/user_data/configs/config.delta.dryrun.json \
    --print-json > "${REPORT_FILE}.raw"

# Check if command failed
if [ $? -ne 0 ]; then
    echo "Command failed."
    cat "${REPORT_FILE}.raw"
    exit 1
fi

# Extract JSON using python
python3 -c "
import sys
import json
import re

try:
    with open('${REPORT_FILE}.raw', 'r') as f:
        content = f.read()

    # Try to find JSON list or dict
    # We look for the largest valid JSON block
    # Simple heuristic: find [ ... ] or { ... }

    # Clean up log lines (lines starting with time or similar)
    # Freqtrade logs usually don't start with [ or {

    # Let's try to load the whole file first, maybe it's clean
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        # Use regex to find list
        match = re.search(r'\[.*\]', content, re.DOTALL)
        if not match:
            # Maybe it's a dict (some versions output dict with 'markets' key)
            match = re.search(r'\{.*\}', content, re.DOTALL)

        if match:
            json_str = match.group(0)
            data = json.loads(json_str)
        else:
            raise Exception('No JSON found')

    # Normalize: we want list of markets
    if isinstance(data, dict):
        if 'markets' in data:
            data = data['markets']
        elif 'pairs' in data:
            data = data['pairs']

    print(f'Successfully parsed {len(data)} markets.')
    with open('${REPORT_FILE}', 'w') as f:
        json.dump(data, f, indent=4)

except Exception as e:
    print(f'Error parsing output: {e}')
    sys.exit(1)
"

if [ $? -ne 0 ]; then
    echo "Parsing failed. Raw output in ${REPORT_FILE}.raw"
    exit 1
fi

echo "Markets saved to ${REPORT_FILE}"
rm "${REPORT_FILE}.raw"

# Validate whitelist existence
echo "Validating Whitelist..."
python3 -c "
import json
import sys

try:
    with open('${REPORT_FILE}', 'r') as f:
        markets = json.load(f)
        # normalize to list of strings if it's object list
        # list-markets --print-json usually returns list of dicts (detailed) or list of strings?
        # Detailed is default.
        if markets and isinstance(markets[0], dict):
            market_symbols = [m['symbol'] for m in markets]
        else:
            market_symbols = markets

    # Load whitelist
    whitelist_file = 'user_data/pairlists/whitelist.delta.json'
    try:
        with open(whitelist_file, 'r') as f:
            wl_data = json.load(f)
            whitelist = wl_data.get('exchange', {}).get('pair_whitelist', [])
    except FileNotFoundError:
        print('Whitelist file not found. Skipping whitelist validation.')
        sys.exit(0)

    missing = [p for p in whitelist if p not in market_symbols]

    if missing:
        print(f'ERROR: {len(missing)} whitelist pairs missing from exchange!')
        for p in missing:
            print(f' - {p}')
        sys.exit(1)

    print('Whitelist validation passed.')

except Exception as e:
    print(f'Error: {e}')
    sys.exit(1)
"

if [ $? -eq 0 ]; then
    echo "SUCCESS: Exchange validation complete."
else
    echo "FAILURE: Validation failed."
    exit 1
fi
