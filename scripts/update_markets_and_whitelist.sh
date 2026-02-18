#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$DIR/common.sh"

export FREQTRADE_CONFIG_FILE="config.delta.dryrun.json"
MARKETS_FILE="user_data/reports/markets_$(date +%Y%m%d_%H%M%S).json"
WHITELIST_FILE="user_data/pairlists/whitelist.delta.json"

# Container paths
CONTAINER_MARKETS_FILE="/freqtrade/$MARKETS_FILE"
CONTAINER_WHITELIST_FILE="/freqtrade/$WHITELIST_FILE"

echo "Fetching markets from Delta ($DELTA_ENV)..."
mkdir -p user_data/reports user_data/pairlists

# Run list-markets
# Capture stdout to file on HOST
docker compose run --rm freqtrade list-markets \
    --config /freqtrade/user_data/configs/config.delta.dryrun.json \
    --exchange delta \
    --trading-mode futures \
    --print-json > "$MARKETS_FILE"

if [ ! -s "$MARKETS_FILE" ]; then
    echo "FAIL: Market fetch returned empty file."
    rm "$MARKETS_FILE"
    exit 1
fi

echo "Validating Market Schema..."
# Locate previous dump for drift check (on HOST)
PREV_DUMP=$(ls -t user_data/reports/markets_*.json 2>/dev/null | grep -v "$MARKETS_FILE" | head -n 1)

# Convert PREV_DUMP to container path if it exists
if [ -n "$PREV_DUMP" ]; then
    CONTAINER_PREV_DUMP="/freqtrade/$PREV_DUMP"
else
    CONTAINER_PREV_DUMP=""
fi

# Run validation inside container
# Python script is at /freqtrade/tools/validate_markets_schema.py (mounted)
docker compose run --rm freqtrade python3 /freqtrade/tools/validate_markets_schema.py "$CONTAINER_MARKETS_FILE" "$CONTAINER_PREV_DUMP"

if [ $? -ne 0 ]; then
    echo "FAIL: Market Schema Validation Failed."
    exit 1
fi

echo "Generating Whitelist..."
# Run generation inside container
# Capture output to file on HOST
docker compose run --rm freqtrade python3 /freqtrade/tools/generate_whitelist.py "$CONTAINER_MARKETS_FILE" > "$WHITELIST_FILE"

if [ $? -eq 0 ]; then
    echo "SUCCESS: Whitelist updated at $WHITELIST_FILE"
    # Print summary (using python on HOST or via container, but simple grep/wc is fine)
    COUNT=$(grep -o "KB/USDT" "$WHITELIST_FILE" | wc -l) # Rough count
    # Or just count lines if formatted
    # But let's use a quick python one-liner on host if python3 available, or container
    # Assuming host might not have python3, use container
    COUNT=$(docker compose run --rm freqtrade python3 -c "import json; print(len(json.load(open('/freqtrade/$WHITELIST_FILE'))['exchange']['pair_whitelist']))")
    echo "Total Pairs: $COUNT"
else
    echo "FAIL: Whitelist generation failed."
    exit 1
fi

# Cleanup old reports (keep last 10)
ls -t user_data/reports/markets_*.json | tail -n +11 | xargs -I {} rm -- {} 2>/dev/null || true
