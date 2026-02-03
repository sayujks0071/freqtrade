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
WHITELIST_TXT="$PAIRLISTS_DIR/whitelist.delta.txt"
VALIDATION_REPORT="$REPORTS_DIR/markets_schema_report_${TIMESTAMP}.md"

mkdir -p $REPORTS_DIR
mkdir -p $PAIRLISTS_DIR

echo "Fetching markets for $DELTA_ENV..."

# Load .env if exists
if [ -f .env ]; then
    # shellcheck disable=SC2046
    export $(cat .env | grep -v '^#' | xargs)
fi

# Fetch markets
TEMP_OUTPUT=$(mktemp)
# We execute freqtrade inside docker.
# Ensure the config exists.
docker compose run --rm freqtrade list-markets \
    --config /freqtrade/user_data/configs/config.delta.dryrun.json \
    --print-json > $TEMP_OUTPUT

if [ $? -ne 0 ]; then
    echo "Failed to fetch markets"
    rm "$TEMP_OUTPUT"
    exit 1
fi

mv "$TEMP_OUTPUT" "$MARKETS_FILE"

echo "Validating schema and checking drift..."

set +e
python3 tools/validate_markets_schema.py \
    --markets "$MARKETS_FILE" \
    --env "$DELTA_ENV" \
    --prev-whitelist "$WHITELIST_JSON" \
    --out-report "$VALIDATION_REPORT"

EXIT_CODE=$?
set -e

if [ $EXIT_CODE -eq 0 ]; then
    echo "Validation PASSED."
    echo "Generating whitelist..."
    python3 tools/generate_whitelist.py "$MARKETS_FILE" > "$WHITELIST_JSON"

    # Generate TXT (extract pairs inside quotes that have a colon)
    grep -o '"[^"]*:[^"]*"' "$WHITELIST_JSON" | tr -d '"' > "$WHITELIST_TXT"

    echo "Whitelist updated at $WHITELIST_JSON"
else
    echo "Validation FAILED (Exit Code: $EXIT_CODE)."
    echo "See report at $VALIDATION_REPORT"
    echo "Whitelist NOT updated."
    exit $EXIT_CODE
fi

# Clean up old dumps (keep last 7)
ls -t $REPORTS_DIR/markets_*.json 2>/dev/null | tail -n +8 | xargs -I {} rm -- {} 2>/dev/null || true

echo "Done."
