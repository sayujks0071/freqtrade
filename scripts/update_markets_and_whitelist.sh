#!/bin/bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$DIR/common.sh"

echo "Updating Markets and Whitelist for Delta ($DELTA_ENV)..."

TIMESTAMP=$(date -u +"%Y%m%d_%H%M%S")
REPORTS_DIR="/freqtrade/user_data/reports"
PAIRLISTS_DIR="/freqtrade/user_data/pairlists"
MARKETS_FILE="$REPORTS_DIR/markets_${TIMESTAMP}.json"

# Create directories (on host first to be safe, though bootstrap does it)
mkdir -p user_data/reports user_data/pairlists

# Find previous dump (on host, to pass path relative to container?)
# No, run inside container.
# Or run 'ls' inside container?
# It's easier to find previous dump on host and pass filename.
PREV_DUMP=$(ls -t user_data/reports/markets_*.json 2>/dev/null | head -n 1)
if [ -n "$PREV_DUMP" ]; then
    # Convert host path to container path
    PREV_DUMP_CONTAINER="/freqtrade/user_data/reports/$(basename "$PREV_DUMP")"
else
    PREV_DUMP_CONTAINER=""
fi

echo "Fetching markets to $MARKETS_FILE..."

# Run fetch_markets.py
docker compose run --rm \
    -e DELTA_ENV \
    -e DELTA_BASE_URL \
    freqtrade python3 /freqtrade/tools/fetch_markets.py \
    --output "$MARKETS_FILE"

if [ $? -ne 0 ]; then
    echo "Failed to fetch markets."
    exit 1
fi

echo "Validating markets..."

# Run validate_markets_schema.py
# Pass PREV_DUMP if exists
VALIDATE_CMD="python3 /freqtrade/tools/validate_markets_schema.py $MARKETS_FILE"
if [ -n "$PREV_DUMP_CONTAINER" ]; then
    VALIDATE_CMD="$VALIDATE_CMD --prev-dump $PREV_DUMP_CONTAINER"
fi

# Pass other args from env
VALIDATE_CMD="$VALIDATE_CMD --min-markets ${MIN_MARKETS:-20} --max-removal-ratio ${MAX_REMOVAL_RATIO:-0.25}"
if [ "$STRICT_VOLUME" = "true" ]; then
    VALIDATE_CMD="$VALIDATE_CMD --strict-volume"
fi

docker compose run --rm freqtrade $VALIDATE_CMD

if [ $? -ne 0 ]; then
    echo "Validation FAILED. Aborting whitelist update."
    exit 1
fi

echo "Validation Passed. Generating whitelist..."

WHITELIST_JSON="$PAIRLISTS_DIR/whitelist.delta.json"
WHITELIST_TXT="$PAIRLISTS_DIR/whitelist.delta.txt"

docker compose run --rm \
    -e FILTER_MODE="${FILTER_MODE:-perps_usdt}" \
    -e ALLOWLIST_REGEX="${ALLOWLIST_REGEX:-.*}" \
    freqtrade python3 /freqtrade/tools/generate_whitelist.py "$MARKETS_FILE" \
    --out-json "$WHITELIST_JSON" \
    --out-txt "$WHITELIST_TXT"

if [ $? -ne 0 ]; then
    echo "Whitelist generation failed."
    exit 1
fi

echo "Whitelist updated: user_data/pairlists/whitelist.delta.json"

# Cleanup old dumps (keep last 7)
# Run on host as it's easier with standard ls/rm
ls -t user_data/reports/markets_*.json | tail -n +8 | xargs -I {} rm -- {} 2>/dev/null || true

echo "Done."
