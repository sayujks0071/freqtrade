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

# Find latest previous dump (optional usage, mostly for debug now)
PREV_DUMP=$(ls -t $REPORTS_DIR/markets_*.json 2>/dev/null | head -n 1 || echo "")

echo "Fetching markets for $DELTA_ENV..."

# Run freqtrade list-markets via Docker
if [ -f .env ]; then
    export $(cat .env | xargs)
fi

TEMP_OUTPUT=$(mktemp)

docker compose run --rm freqtrade list-markets \
    --config /freqtrade/user_data/configs/config.delta.dryrun.json \
    --print-json > $TEMP_OUTPUT

if [ $? -ne 0 ]; then
    echo "Failed to fetch markets"
    rm $TEMP_OUTPUT
    exit 1
fi

mv $TEMP_OUTPUT $MARKETS_FILE

# Validation
WHITELIST_JSON="$PAIRLISTS_DIR/whitelist.delta.json"
REPORT_FILE="$REPORTS_DIR/markets_schema_report_${TIMESTAMP}.md"

echo "Validating schema..."
PREV_WL_ARG=""
if [ -f "$WHITELIST_JSON" ]; then
    PREV_WL_ARG="--prev-whitelist $WHITELIST_JSON"
fi

# Run validation. If it fails, we exit 1 (set -e handles it if we don't catch it, but we want custom message)
set +e
python3 tools/validate_markets_schema.py \
    --markets "$MARKETS_FILE" \
    --env "$DELTA_ENV" \
    $PREV_WL_ARG \
    --out-report "$REPORT_FILE"
EXIT_CODE=$?
set -e

if [ $EXIT_CODE -ne 0 ]; then
    echo "❌ Validation FAILED. See report: $REPORT_FILE"
    # Cat the report to stdout for CI visibility
    cat "$REPORT_FILE"
    exit 1
fi

echo "✅ Validation Passed."

echo "Generating whitelist..."
WHITELIST_TXT="$PAIRLISTS_DIR/whitelist.delta.txt"

python3 tools/generate_whitelist.py "$MARKETS_FILE" > "$WHITELIST_JSON"

# Also generate TXT list (symbols only)
grep -o '"[^"]*:[^"]*"' "$WHITELIST_JSON" | tr -d '"' > "$WHITELIST_TXT"

echo "Whitelist updated at $WHITELIST_JSON"

# Clean up old dumps (keep last 7)
ls -t $REPORTS_DIR/markets_*.json | tail -n +8 | xargs -I {} rm -- {} 2>/dev/null || true

echo "Done."
