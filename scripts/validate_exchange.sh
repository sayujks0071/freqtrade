#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$DIR/common.sh"

TIMESTAMP=$(date -u +"%Y%m%d_%H%M%S")
REPORT_FILE="user_data/reports/markets_${TIMESTAMP}.json"
CONFIG_FILE="/freqtrade/user_data/configs/config.delta.dryrun.json"

echo "Fetching markets from Delta (${DELTA_ENV:-default})..."

# Run list-markets
# We use --print-json to get the raw list
docker compose run --rm freqtrade list-markets \
    --config "$CONFIG_FILE" \
    --exchange delta \
    --trading-mode futures \
    --print-json > "${REPORT_FILE}.tmp"

# Extract JSON array (lines starting with [)
grep -o '\[.*\]' "${REPORT_FILE}.tmp" > "$REPORT_FILE"

if [ ! -s "$REPORT_FILE" ]; then
    echo "Error: Failed to fetch markets or parse output."
    echo "Raw Output:"
    cat "${REPORT_FILE}.tmp"
    rm -f "$REPORT_FILE" "${REPORT_FILE}.tmp"
    exit 1
fi
rm "${REPORT_FILE}.tmp"

echo "Markets list saved to $REPORT_FILE"

echo "Validating Whitelist..."

# Python script to check whitelist
python3 -c "
import json
import sys
import os

try:
    with open('$REPORT_FILE', 'r') as f:
        markets = json.load(f) # List of pair strings

    whitelist_file = 'user_data/pairlists/whitelist.delta.json'
    if not os.path.exists(whitelist_file):
        print(f'Warning: Whitelist file {whitelist_file} not found. Skipping validation.')
        sys.exit(0)

    with open(whitelist_file, 'r') as f:
        whitelist = json.load(f)

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
else
    echo "Validation Failed."
    exit 1
fi
