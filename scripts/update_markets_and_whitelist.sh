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
REPORT_FILE="$REPORTS_DIR/markets_schema_report_${TIMESTAMP}.md"

mkdir -p $REPORTS_DIR
mkdir -p $PAIRLISTS_DIR

echo "Fetching markets for $DELTA_ENV..."

# Run freqtrade list-markets via Docker
if [ -f .env ]; then
    export $(cat .env | xargs)
fi

TEMP_OUTPUT=$(mktemp)

# Command to fetch markets.
# We explicitly set config to delta dryrun (or any config with exchange delta)
# Note: This might fail if the config refers to files not mounted or env vars not set.
# But existing script did this, so we assume it works.
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
echo "Markets saved to $MARKETS_FILE"

echo "Validating schema and drift..."

# We temporarily disable set -e to handle the validation exit code manually
set +e
python3 tools/validate_markets_schema.py \
    --markets "$MARKETS_FILE" \
    --env "$DELTA_ENV" \
    --prev-whitelist "$WHITELIST_JSON" \
    --out-report "$REPORT_FILE"

VALIDATION_EXIT_CODE=$?
set -e

if [ $VALIDATION_EXIT_CODE -ne 0 ]; then
    echo "Validation FAILED (Exit Code: $VALIDATION_EXIT_CODE). See $REPORT_FILE"
    echo "Whitelist NOT updated."
    # Exit with failure to signal CI
    exit 1
fi

echo "Validation PASSED. Generating whitelist..."

python3 tools/generate_whitelist.py "$MARKETS_FILE" > "$WHITELIST_JSON"

# Also generate TXT list (symbols only)
grep -o '"[^"]*:[^"]*"' "$WHITELIST_JSON" | tr -d '"' > "$WHITELIST_TXT"

echo "Whitelist updated at $WHITELIST_JSON"

# Clean up old dumps (keep last 7)
ls -t $REPORTS_DIR/markets_*.json | tail -n +8 | xargs -I {} rm -- {} 2>/dev/null || true

echo "Done."
