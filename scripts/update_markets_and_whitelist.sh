#!/bin/bash
set -e

# Ensure root
cd "$(dirname "$0")/.."

DELTA_ENV=${DELTA_ENV:-india_testnet}
TIMESTAMP=$(date -u +"%Y%m%d_%H%M%S")
REPORTS_DIR="user_data/reports"
PAIRLISTS_DIR="user_data/pairlists"
WHITELIST_FILE="$PAIRLISTS_DIR/whitelist.delta.json"
MARKETS_FILE="$REPORTS_DIR/markets_${TIMESTAMP}.json"
REPORT_FILE="$REPORTS_DIR/markets_schema_report_${TIMESTAMP}.md"

mkdir -p $REPORTS_DIR
mkdir -p $PAIRLISTS_DIR

echo "Fetching markets for $DELTA_ENV..."

if [ -f .env ]; then
    export $(cat .env | xargs)
fi

TEMP_MARKETS=$(mktemp)

# Fetch markets to temp file
# We use config.delta.dryrun.json as reference for credentials/exchange settings.
docker compose run --rm freqtrade list-markets \
    --config /freqtrade/user_data/configs/config.delta.dryrun.json \
    --print-json > $TEMP_MARKETS

if [ $? -ne 0 ]; then
    echo "Failed to fetch markets"
    rm $TEMP_MARKETS
    exit 1
fi

# Determine previous whitelist for drift check
PREV_WHITELIST_ARG=""
if [ -f "$WHITELIST_FILE" ]; then
    PREV_WHITELIST_ARG="--prev-whitelist $WHITELIST_FILE"
fi

echo "Validating schema..."
# Run validator. Disable exit on error for this command to handle the code.
set +e
python3 tools/validate_markets_schema.py \
    --markets "$TEMP_MARKETS" \
    --env "$DELTA_ENV" \
    $PREV_WHITELIST_ARG \
    --out-report "$REPORT_FILE"

VALIDATOR_EXIT_CODE=$?
set -e

if [ $VALIDATOR_EXIT_CODE -eq 0 ]; then
    echo "Validation PASS. Updating whitelist..."

    # Move temp markets to final
    mv "$TEMP_MARKETS" "$MARKETS_FILE"

    # Generate whitelist
    python3 tools/generate_whitelist.py "$MARKETS_FILE" > "$WHITELIST_FILE"

    # Generate TXT
    WHITELIST_TXT="$PAIRLISTS_DIR/whitelist.delta.txt"
    grep -o '"[^"]*:[^"]*"' "$WHITELIST_FILE" | tr -d '"' > "$WHITELIST_TXT"

    echo "Whitelist updated at $WHITELIST_FILE"
else
    echo "Validation FAILED. See report at $REPORT_FILE"

    # Save failed markets dump for debugging
    FAILED_MARKETS_FILE="$REPORTS_DIR/markets_failed_${TIMESTAMP}.json"
    mv "$TEMP_MARKETS" "$FAILED_MARKETS_FILE"
    echo "Failed markets dump saved to $FAILED_MARKETS_FILE"

    exit $VALIDATOR_EXIT_CODE
fi

# Clean up old dumps (keep last 7)
ls -t $REPORTS_DIR/markets_*.json 2>/dev/null | tail -n +8 | xargs -I {} rm -- {} 2>/dev/null || true

echo "Done."
