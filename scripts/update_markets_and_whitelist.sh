#!/bin/bash
set -e

# Ensure root
cd "$(dirname "$0")/.."

# Load environment
if [ -f .env ]; then
    export $(cat .env | xargs)
fi

DELTA_ENV=${DELTA_ENV:-india_testnet}
TIMESTAMP=$(date -u +"%Y%m%d_%H%M%S")
REPORTS_DIR="user_data/reports"
PAIRLISTS_DIR="user_data/pairlists"
MARKETS_FILE="$REPORTS_DIR/markets_${TIMESTAMP}.json"
REPORT_FILE="$REPORTS_DIR/markets_schema_report_${TIMESTAMP}.md"
WHITELIST_JSON="$PAIRLISTS_DIR/whitelist.delta.json"
WHITELIST_TXT="$PAIRLISTS_DIR/whitelist.delta.txt"

mkdir -p $REPORTS_DIR
mkdir -p $PAIRLISTS_DIR

echo "Fetching markets for $DELTA_ENV..."

TEMP_MARKETS=$(mktemp)
TEMP_WHITELIST=$(mktemp)

# Command to fetch markets.
# We explicitly set config to delta dryrun.
# We assume freqtrade list-markets --print-json outputs valid JSON to stdout.
if ! docker compose run --rm freqtrade list-markets \
    --config /freqtrade/user_data/configs/config.delta.dryrun.json \
    --print-json > $TEMP_MARKETS; then
    echo "Failed to fetch markets"
    rm $TEMP_MARKETS $TEMP_WHITELIST
    exit 1
fi

echo "Generating candidate whitelist..."
if ! python3 tools/generate_whitelist.py "$TEMP_MARKETS" > "$TEMP_WHITELIST"; then
    echo "Failed to generate whitelist"
    rm $TEMP_MARKETS $TEMP_WHITELIST
    exit 1
fi

echo "Validating schema & drift..."
# Run validator. If it fails, we capture failure but still want to see the report path.
set +e
python3 tools/validate_markets_schema.py \
    --markets "$TEMP_MARKETS" \
    --candidate-whitelist "$TEMP_WHITELIST" \
    --prev-whitelist "$WHITELIST_JSON" \
    --env "$DELTA_ENV" \
    --out-report "$REPORT_FILE"

VALIDATOR_EXIT=$?
set -e

if [ $VALIDATOR_EXIT -eq 0 ]; then
    echo "Validation PASS. Updating files..."
    mv $TEMP_MARKETS $MARKETS_FILE
    mv $TEMP_WHITELIST $WHITELIST_JSON

    # Generate TXT list
    grep -o '"[^"]*:[^"]*"' "$WHITELIST_JSON" | tr -d '"' > "$WHITELIST_TXT"

    echo "Whitelist updated at $WHITELIST_JSON"
    echo "Report at $REPORT_FILE"

    # Clean up old dumps (keep last 7)
    ls -t $REPORTS_DIR/markets_*.json 2>/dev/null | tail -n +8 | xargs -I {} rm -- {} 2>/dev/null || true
    ls -t $REPORTS_DIR/markets_schema_report_*.md 2>/dev/null | tail -n +8 | xargs -I {} rm -- {} 2>/dev/null || true

else
    echo "Validation FAIL (Exit code $VALIDATOR_EXIT). Check report at $REPORT_FILE"
    mv $TEMP_MARKETS "${REPORTS_DIR}/markets_failed_${TIMESTAMP}.json"
    rm $TEMP_WHITELIST
    exit 1
fi
