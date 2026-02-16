#!/bin/bash
set -e

# Ensure we are in the repo root
cd "$(dirname "$0")/.."

# Source common environment setup
source scripts/common.sh

echo "Starting Exchange Validation for Delta ($DELTA_ENV)..."
echo "Target Base URL: $DELTA_BASE_URL"

# Step 1: Check if 'delta' exchange is available in ccxt (via freqtrade)
echo "1. verifying 'delta' exchange availability..."
docker compose run --rm freqtrade list-exchanges --print-one-column | grep -q "delta"
if [ $? -eq 0 ]; then
    echo "SUCCESS: 'delta' exchange found."
else
    echo "FAIL: 'delta' exchange NOT found in freqtrade/ccxt."
    exit 1
fi

# Step 2: Fetch Markets
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
MARKETS_FILE="user_data/reports/markets_${TIMESTAMP}.json"
LATEST_MARKETS_FILE="user_data/reports/markets_latest.json"

echo "2. Fetching markets to $MARKETS_FILE..."
# We use a temporary file to capture output, ensuring we don't get docker logs mixed in if possible.
# Freqtrade logs to stderr, JSON to stdout.
docker compose run --rm freqtrade list-markets --exchange delta --trading-mode futures --print-json > "$MARKETS_FILE"

# Basic validation that file is not empty and contains JSON
if [ ! -s "$MARKETS_FILE" ]; then
    echo "FAIL: Markets file is empty."
    exit 1
fi

# Create a symlink or copy to latest for easy access
cp "$MARKETS_FILE" "$LATEST_MARKETS_FILE"

# Step 3: Validate Markets Schema and Whitelist
# We check against the dryrun config by default, or the one specified in ENV
CONFIG_FILE=${FREQTRADE_CONFIG_FILE:-config.delta.dryrun.json}
CONFIG_PATH="/freqtrade/user_data/configs/$CONFIG_FILE"

echo "3. Validating markets and whitelist in $CONFIG_FILE..."

docker compose run --rm --entrypoint python3 freqtrade \
    /freqtrade/tools/validate_markets_schema.py \
    "/freqtrade/$LATEST_MARKETS_FILE" \
    --config "$CONFIG_PATH"

# Also validate the generated whitelist file
WHITELIST_FILE="/freqtrade/user_data/pairlists/whitelist.delta.json"
echo "Validating generated whitelist in $WHITELIST_FILE..."

docker compose run --rm --entrypoint python3 freqtrade \
    /freqtrade/tools/validate_markets_schema.py \
    "/freqtrade/$LATEST_MARKETS_FILE" \
    --config "$WHITELIST_FILE"

if [ $? -eq 0 ]; then
    echo "SUCCESS: Validation passed."
else
    echo "FAIL: Validation failed."
    exit 1
fi

# Check Time Drift
echo "4. Checking time drift..."
# Simple check: Compare local time with a time server or just print it.
# The container time should be UTC.
docker compose run --rm --entrypoint sh freqtrade -c "date -u"
echo "Local time: $(date -u)"
echo "Ensure these match closely."

echo "Validation Complete."
