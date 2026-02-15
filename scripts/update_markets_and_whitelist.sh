#!/bin/bash
set -e

# Ensure root
cd "$(dirname "$0")/.."

DELTA_ENV=${DELTA_ENV:-india_testnet}
TIMESTAMP=$(date -u +"%Y%m%d_%H%M%S")
REPORTS_DIR="user_data/reports"
PAIRLISTS_DIR="user_data/pairlists"
MARKETS_FILE="$REPORTS_DIR/markets_${TIMESTAMP}.json"
WHITELIST_JSON="$PAIRLISTS_DIR/whitelist.delta.json"
REPORT_FILE="$REPORTS_DIR/markets_schema_report_${TIMESTAMP}.md"

mkdir -p $REPORTS_DIR
mkdir -p $PAIRLISTS_DIR

# Find latest previous dump
PREV_DUMP=$(ls -t $REPORTS_DIR/markets_*.json 2>/dev/null | head -n 1 || echo "")

echo "Fetching markets for $DELTA_ENV..."

# Run freqtrade list-markets via Docker
if [ -f .env ]; then
    export $(cat .env | xargs)
fi

TEMP_OUTPUT=$(mktemp)

# Command to fetch markets.
docker compose run --rm freqtrade list-markets \
    --config /freqtrade/user_data/configs/config.delta.dryrun.json \
    --print-json > $TEMP_OUTPUT

# Check if successful
if [ $? -ne 0 ]; then
    echo "Failed to fetch markets"
    rm $TEMP_OUTPUT
    exit 1
fi

mv $TEMP_OUTPUT $MARKETS_FILE

echo "Validating schema and checking drift..."
# We allow the python script to control the exit code.
# If it fails (exit 2), this script will exit due to set -e, but we want to print a message first.
# So we disable set -e temporarily or use if.

set +e
python3 tools/validate_markets_schema.py \
    --markets "$MARKETS_FILE" \
    --prev-whitelist "$WHITELIST_JSON" \
    --env "$DELTA_ENV" \
    --out-report "$REPORT_FILE"

VALIDATION_EXIT_CODE=$?
set -e

if [ $VALIDATION_EXIT_CODE -ne 0 ]; then
    echo "Validation FAILED (Exit Code: $VALIDATION_EXIT_CODE). See report at $REPORT_FILE"
    exit $VALIDATION_EXIT_CODE
fi

echo "Validation PASSED."
echo "Generating whitelist..."

WHITELIST_TXT="$PAIRLISTS_DIR/whitelist.delta.txt"

python3 tools/generate_whitelist.py "$MARKETS_FILE" > "$WHITELIST_JSON"

# Also generate TXT list (symbols only)
grep -o '"[^"]*:[^"]*"' "$WHITELIST_JSON" | tr -d '"' > "$WHITELIST_TXT"

echo "Whitelist updated at $WHITELIST_JSON"

# Clean up old dumps (keep last 7)
ls -t $REPORTS_DIR/markets_*.json | tail -n +8 | xargs -I {} rm -- {} 2>/dev/null || true

echo "Done."
