#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$DIR/common.sh"

REPORT_FILE="user_data/reports/markets_$(date +%s).json"
# We use dryrun config for validation connection
CONFIG_FILE="/freqtrade/user_data/configs/config.delta.dryrun.json"

echo "Fetching markets from Delta ($DELTA_ENV)..."

# Ensure report dir exists
mkdir -p user_data/reports

# Run list-markets
# We expect JSON output.
# We explicitly pass the config file path inside the container.
# docker compose run picks up env vars from .env file defined in docker-compose.yml
# But we also export them in common.sh just in case we run local python tools.

# Using a temp file to capture output
TEMP_OUT=$(mktemp)

echo "Running freqtrade list-markets..."
docker compose run --rm freqtrade list-markets \
    --config "$CONFIG_FILE" \
    --exchange delta \
    --trading-mode futures \
    --print-json > "$TEMP_OUT"

if [ $? -ne 0 ]; then
    echo "ERROR: Failed to run list-markets."
    cat "$TEMP_OUT"
    rm "$TEMP_OUT"
    exit 1
fi

# Extract JSON array (lines starting with [)
# Sometimes freqtrade logs to stdout even with print-json if not configured perfectly.
# We look for the JSON list.
grep -o '\[.*\]' "$TEMP_OUT" > "$REPORT_FILE"

rm "$TEMP_OUT"

if [ ! -s "$REPORT_FILE" ]; then
    echo "ERROR: Output file is empty or invalid."
    exit 1
fi

echo "Markets list saved to $REPORT_FILE"

# Validate that whitelist pairs exist in the dump
# We use the existing python tool if suitable or a simple python script here.
# The 'tools/generate_whitelist.py' generates a whitelist FROM the dump.
# The user wants to "validate that whitelist pairs in config exist in that markets dump".
# But our config (dryrun.json) has EMPTY whitelist. The actual whitelist is in 'whitelist.delta.json'.
# So we should validate 'whitelist.delta.json' against the dump.

if [ -f user_data/pairlists/whitelist.delta.json ]; then
    echo "Validating existing whitelist against market dump..."
    python3 -c "
import json
import sys

try:
    with open('$REPORT_FILE', 'r') as f:
        markets = json.load(f)
        market_symbols = {m['symbol'] for m in markets}

    with open('user_data/pairlists/whitelist.delta.json', 'r') as f:
        wl_data = json.load(f)
        whitelist = wl_data.get('exchange', {}).get('pair_whitelist', [])

    missing = [p for p in whitelist if p not in market_symbols]

    if missing:
        print('ERROR: The following whitelist pairs are not in the market dump:')
        for m in missing:
            print(f' - {m}')
        sys.exit(1)

    print(f'SUCCESS: All {len(whitelist)} whitelist pairs found in market dump.')

except Exception as e:
    print(f'Validation Error: {e}')
    sys.exit(1)
"
    if [ $? -ne 0 ]; then
        exit 1
    fi
else
    echo "No whitelist found. Generating one..."
    # If no whitelist, we generate it using the tool
    python3 tools/generate_whitelist.py "$REPORT_FILE" > user_data/pairlists/whitelist.delta.json
    echo "Generated new whitelist at user_data/pairlists/whitelist.delta.json"
fi

echo "Exchange validation complete."
