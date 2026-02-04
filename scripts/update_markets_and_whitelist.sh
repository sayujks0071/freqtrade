#!/bin/bash
set -e

# Ensure root
cd "$(dirname "$0")/.."

DELTA_ENV=${DELTA_ENV:-india_testnet}
TIMESTAMP=$(date -u +"%Y%m%d_%H%M%S")
REPORTS_DIR="user_data/reports"
PAIRLISTS_DIR="user_data/pairlists"
MARKETS_FILE="$REPORTS_DIR/markets_${TIMESTAMP}.json"

mkdir -p $REPORTS_DIR
mkdir -p $PAIRLISTS_DIR

echo "Fetching markets for $DELTA_ENV..."

# Load .env if exists
if [ -f .env ]; then
    export $(cat .env | xargs)
fi

# We use a temporary file for the docker output because of potential log noise
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

echo "Validating schema..."
PREV_WHITELIST="$PAIRLISTS_DIR/whitelist.delta.json"
REPORT_FILE="$REPORTS_DIR/markets_schema_report_${TIMESTAMP}.md"

# Run validation
# We temporarily disable 'set -e' to capture exit code cleanly or just let it fail?
# The requirement: "Exit non-zero so CI fails".
# But we want to print a message first.
set +e
python3 tools/validate_markets_schema.py \
    --markets "$MARKETS_FILE" \
    --env "$DELTA_ENV" \
    --prev-whitelist "$PREV_WHITELIST" \
    --out-report "$REPORT_FILE"
EXIT_CODE=$?
set -e

if [ $EXIT_CODE -ne 0 ]; then
    echo "❌ Validation FAILED. Whitelist will NOT be updated."
    echo "Report generated at: $REPORT_FILE"
    exit 1
fi

echo "✅ Validation PASSED."

echo "Generating whitelist..."
WHITELIST_JSON="$PAIRLISTS_DIR/whitelist.delta.json"
WHITELIST_TXT="$PAIRLISTS_DIR/whitelist.delta.txt"

python3 tools/generate_whitelist.py "$MARKETS_FILE" > "$WHITELIST_JSON"

# Also generate TXT list (symbols only)
grep -o '"[^"]*:[^"]*"' "$WHITELIST_JSON" | tr -d '"' > "$WHITELIST_TXT"

echo "Whitelist updated at $WHITELIST_JSON"

# Clean up old dumps (keep last 7)
ls -t $REPORTS_DIR/markets_*.json 2>/dev/null | tail -n +8 | xargs -I {} rm -- {} 2>/dev/null || true

echo "Done."
