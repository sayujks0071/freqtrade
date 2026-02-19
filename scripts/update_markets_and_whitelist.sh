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

# Run freqtrade list-markets via Docker
# Note: Ensure .env is loaded or vars passed
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

# Report path
REPORT_FILE="$REPORTS_DIR/markets_schema_report_${TIMESTAMP}.md"
WHITELIST_JSON="$PAIRLISTS_DIR/whitelist.delta.json"

echo "Validating schema..."
# Temporarily disable set -e for the validation step to handle the exit code manually
set +e
python3 tools/validate_markets_schema.py \
    --markets "$MARKETS_FILE" \
    --env "$DELTA_ENV" \
    --prev-whitelist "$WHITELIST_JSON" \
    --out-report "$REPORT_FILE"

VALIDATION_EXIT_CODE=$?
set -e

if [ $VALIDATION_EXIT_CODE -ne 0 ]; then
    echo "Validation FAILED (Exit Code: $VALIDATION_EXIT_CODE). Check report at $REPORT_FILE"
    # Ensure the report is visible or handled by CI
    # We exit with the same error code to fail the CI job
    exit $VALIDATION_EXIT_CODE
fi

echo "Validation PASSED. Generating whitelist..."
WHITELIST_TXT="$PAIRLISTS_DIR/whitelist.delta.txt"

python3 tools/generate_whitelist.py "$MARKETS_FILE" > "$WHITELIST_JSON"

# Also generate TXT list (symbols only)
grep -o '"[^"]*:[^"]*"' "$WHITELIST_JSON" | tr -d '"' > "$WHITELIST_TXT"

echo "Whitelist updated at $WHITELIST_JSON"

# Clean up old dumps (keep last 7)
ls -t $REPORTS_DIR/markets_*.json | tail -n +8 | xargs -I {} rm -- {} 2>/dev/null || true

echo "Done."
