#!/bin/bash
set -e
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$DIR/common.sh"

echo "Validating Delta Exchange Connection..."
echo "Environment: $DELTA_ENV"
echo "Base URL: $BASE_URL"

# 1. Connectivity Check (ping)
echo "Checking connectivity..."
if ! curl -s -f -o /dev/null "$BASE_URL/v2/products"; then
    echo "FAIL: Could not connect to $BASE_URL"
    exit 1
fi
echo "Connectivity OK."

# 2. Market Data Validation (using existing tool)
echo "Validating Market Data Schema..."
# We reuse the update script's logic but in a check-only mode if possible,
# or just run the update script which validates everything.
# But validate_exchange should be lighter.
# Let's fetch markets and run the validator.

TEMP_MARKETS=$(mktemp)
echo "Fetching markets..."
docker compose run --rm freqtrade list-markets \
    --config /freqtrade/user_data/configs/config.delta.dryrun.json \
    --print-json > "$TEMP_MARKETS.raw"

# Extract JSON
python3 -c "
import sys, json, re
try:
    content = open('$TEMP_MARKETS.raw').read()
    match = re.search(r'\[.*\]', content, re.DOTALL)
    if match:
        print(match.group(0))
    else:
        sys.exit(1)
except:
    sys.exit(1)
" > "$TEMP_MARKETS"

if [ ! -s "$TEMP_MARKETS" ]; then
    echo "FAIL: Failed to fetch/parse markets"
    rm "$TEMP_MARKETS"*
    exit 1
fi

echo "Running Schema Validator..."
python3 tools/validate_markets_schema.py "$TEMP_MARKETS"
VALID_STATUS=$?

rm "$TEMP_MARKETS"*

if [ $VALID_STATUS -eq 0 ]; then
    echo "PASS: Market Data Schema is valid."
else
    echo "FAIL: Market Data Schema validation failed."
    exit 1
fi

echo "Exchange Validation Complete: SUCCESS"
