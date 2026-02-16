#!/bin/bash
set -e

# Load env
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

DELTA_ENV=${DELTA_ENV:-india_prod}
FILTER_MODE=${FILTER_MODE:-perps_usdt}
DATE_STR=$(date -u +"%Y-%m-%d_%H%M%S")
MARKETS_FILE="user_data/reports/markets_${DATE_STR}.json"
REPORT_FILE="user_data/reports/markets_schema_report_${DATE_STR}.md"
WHITELIST_JSON="user_data/pairlists/whitelist.delta.json"
WHITELIST_TXT="user_data/pairlists/whitelist.delta.txt"
PREV_WHITELIST=$WHITELIST_JSON

echo "Fetching markets for $DELTA_ENV..."

# Ensure reports dir exists
mkdir -p user_data/reports

# Determine command
CMD_PREFIX=""
if command -v freqtrade &> /dev/null; then
    CMD_PREFIX="freqtrade"
elif command -v docker &> /dev/null; then
    CMD_PREFIX="docker compose run --rm freqtrade"
else
    echo "Error: Neither freqtrade nor docker found."
    exit 1
fi

echo "Using command: $CMD_PREFIX"

# Fetch markets
# output to temporary file first to check for docker logs pollution
TEMP_OUT="temp_markets.json"

$CMD_PREFIX list-markets \
    --config user_data/configs/config.delta.dryrun.json \
    --print-json > "$TEMP_OUT"

# Move to final location (assuming valid json, validation step will catch if not)
mv "$TEMP_OUT" "$MARKETS_FILE"

echo "Markets dumped to $MARKETS_FILE"

# Validate
echo "Validating markets..."
# Ensure PYTHONPATH includes current dir for tools import
export PYTHONPATH=$PYTHONPATH:.

python3 tools/validate_markets_schema.py \
    --markets "$MARKETS_FILE" \
    --prev-whitelist "$PREV_WHITELIST" \
    --out-report "$REPORT_FILE"

RET=$?
if [ $RET -ne 0 ]; then
    echo "Validation FAILED. Check $REPORT_FILE"
    exit $RET
fi

echo "Validation PASSED."

# Generate Whitelist
echo "Generating whitelist..."

python3 -c "
import json
import sys
import os
# Ensure tools is in path
sys.path.append(os.getcwd())
from tools.validate_markets_schema import is_eligible

with open('$MARKETS_FILE', 'r') as f:
    markets = json.load(f)

whitelist = [m['symbol'] for m in markets if is_eligible(m)]
whitelist.sort()

# Write JSON
out_json = {'exchange': {'pair_whitelist': whitelist}}
with open('$WHITELIST_JSON', 'w') as f:
    json.dump(out_json, f, indent=4)

# Write TXT
with open('$WHITELIST_TXT', 'w') as f:
    f.write('\n'.join(whitelist))

print(f'Whitelist generated with {len(whitelist)} pairs.')
"

echo "Done."
