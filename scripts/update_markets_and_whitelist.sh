#!/bin/bash
set -e

# Ensure root
cd "$(dirname "$0")/.."

DELTA_ENV=${DELTA_ENV:-india_testnet}
TIMESTAMP=$(date -u +"%Y%m%d_%H%M%S")
REPORTS_DIR="user_data/reports"
PAIRLISTS_DIR="user_data/pairlists"
MARKETS_FILE="$REPORTS_DIR/markets_${TIMESTAMP}.json"
REPORT_FILE="$REPORTS_DIR/markets_schema_report_${TIMESTAMP}.md"

mkdir -p $REPORTS_DIR
mkdir -p $PAIRLISTS_DIR

# Define whitelist path
WHITELIST_JSON="$PAIRLISTS_DIR/whitelist.delta.json"
WHITELIST_TXT="$PAIRLISTS_DIR/whitelist.delta.txt"

echo "Fetching markets for $DELTA_ENV..."

# Load .env
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Temp file for raw output
TEMP_OUTPUT=$(mktemp)

# Determine config file based on ENV if needed, or default to dryrun which has Delta exchange config
# Note: We use dryrun config as it contains the exchange connection settings.
# This does not execute any trades, only fetches markets.
CONFIG_FILE="user_data/configs/config.delta.dryrun.json"

# Run freqtrade list-markets via Docker
# Note: Ensure we use the correct image and config
docker compose run --rm freqtrade list-markets \
    --config /freqtrade/$CONFIG_FILE \
    --print-json > $TEMP_OUTPUT

# Check docker exit code
if [ $? -ne 0 ]; then
    echo "Failed to fetch markets"
    rm $TEMP_OUTPUT
    exit 1
fi

# Move to final location
mv $TEMP_OUTPUT $MARKETS_FILE
echo "Markets saved to $MARKETS_FILE"

echo "Validating schema..."

# Run validator
# It compares against the CURRENT whitelist (before update) to check drift
if ! python3 tools/validate_markets_schema.py \
    --markets "$MARKETS_FILE" \
    --prev-whitelist "$WHITELIST_JSON" \
    --env "$DELTA_ENV" \
    --out-report "$REPORT_FILE"; then

    echo "Validation FAILED. See report at $REPORT_FILE"
    echo "Whitelist NOT updated."
    # Exit with failure to signal CI
    exit 1
fi

echo "Validation PASSED."
echo "Generating whitelist..."

python3 tools/generate_whitelist.py "$MARKETS_FILE" > "$WHITELIST_JSON"

# Also generate TXT list (symbols only)
grep -o '"[^"]*:[^"]*"' "$WHITELIST_JSON" | tr -d '"' > "$WHITELIST_TXT"

echo "Whitelist updated at $WHITELIST_JSON"

# Clean up old dumps (keep last 7)
ls -t $REPORTS_DIR/markets_*.json 2>/dev/null | tail -n +8 | xargs -I {} rm -- {} 2>/dev/null || true
ls -t $REPORTS_DIR/markets_schema_report_*.md 2>/dev/null | tail -n +8 | xargs -I {} rm -- {} 2>/dev/null || true

echo "Done."
