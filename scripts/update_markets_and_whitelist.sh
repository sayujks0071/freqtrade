#!/bin/bash
set -e

# Setup Environment
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$SCRIPT_DIR/.."
source "$SCRIPT_DIR/common.sh"

FILTER_MODE="${FILTER_MODE:-perps_usdt}"
MIN_MARKETS="${MIN_MARKETS:-20}"
MAX_REMOVAL_RATIO="${MAX_REMOVAL_RATIO:-0.25}"

echo "Starting Market Refresh & Whitelist Update..."
echo "Filter Mode: $FILTER_MODE"
echo "Min Markets: $MIN_MARKETS"
echo "Max Removal Ratio: $MAX_REMOVAL_RATIO"

# Prepare paths
MARKETS_DUMP="$BASE_DIR/user_data/reports/markets_dump.json"
NEW_WHITELIST="$BASE_DIR/user_data/reports/new_whitelist.json"
SCHEMA_REPORT="$BASE_DIR/user_data/reports/markets_schema_report.md"
CURRENT_WHITELIST_FILE="$BASE_DIR/user_data/pairlists/whitelist.delta.json"

# 1. Fetch Markets Dump
echo "Fetching markets from Delta Exchange ($DELTA_ENV)..."
# We use freqtrade list-markets.
# We need to ensure freqtrade command is available.
if ! command -v freqtrade &> /dev/null; then
    echo "freqtrade command not found! Trying via python -m freqtrade..."
    FREQTRADE_CMD="python -m freqtrade"
else
    FREQTRADE_CMD="freqtrade"
fi

$FREQTRADE_CMD list-markets --exchange delta --print-json > "$MARKETS_DUMP"

if [ ! -s "$MARKETS_DUMP" ]; then
    echo "Error: Markets dump is empty!"
    exit 1
fi

echo "Markets dump saved to $MARKETS_DUMP"

# 2. Generate Candidate Whitelist
echo "Generating candidate whitelist..."
python "$BASE_DIR/tools/generate_whitelist.py" \
    --markets "$MARKETS_DUMP" \
    --out "$NEW_WHITELIST"

if [ ! -s "$NEW_WHITELIST" ]; then
    echo "Error: Generated whitelist is empty!"
    exit 1
fi

echo "Candidate whitelist generated at $NEW_WHITELIST"

# 3. Validate Schema & Drift
echo "Validating schema and checking drift..."
# Pass current whitelist if it exists for drift check
PREV_WHITELIST_ARG=""
if [ -f "$CURRENT_WHITELIST_FILE" ]; then
    PREV_WHITELIST_ARG="--prev-whitelist $CURRENT_WHITELIST_FILE"
fi

python "$BASE_DIR/tools/validate_markets_schema.py" \
    --markets "$MARKETS_DUMP" \
    --candidate-whitelist "$NEW_WHITELIST" \
    $PREV_WHITELIST_ARG \
    --env "$DELTA_ENV" \
    --out-report "$SCHEMA_REPORT"

VALIDATION_EXIT_CODE=$?

if [ $VALIDATION_EXIT_CODE -ne 0 ]; then
    echo "Validation FAILED! See report at $SCHEMA_REPORT"
    cat "$SCHEMA_REPORT"
    exit $VALIDATION_EXIT_CODE
fi

echo "Validation PASSED."

# 4. Update Whitelist
echo "Updating whitelist file..."
cp "$NEW_WHITELIST" "$CURRENT_WHITELIST_FILE"
# Also save a text version for easy reading
# jq -r '.[]' "$CURRENT_WHITELIST_FILE" > "${CURRENT_WHITELIST_FILE%.json}.txt"

echo "Whitelist updated successfully: $CURRENT_WHITELIST_FILE"
cat "$SCHEMA_REPORT"
