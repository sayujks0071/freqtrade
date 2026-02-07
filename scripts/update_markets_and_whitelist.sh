#!/bin/bash
set -e

# Ensure root
cd "$(dirname "$0")/.."

# Load env if present
if [ -f .env ]; then
    # Load env vars, ignoring comments
    export $(grep -v '^#' .env | xargs)
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

# We use a temporary file for the docker output
TEMP_OUTPUT=$(mktemp)

# Determine config file based on env or default to dryrun
CONFIG_FILE="user_data/configs/config.delta.dryrun.json"

# Run freqtrade list-markets
# We map the output to a file.
docker compose run --rm freqtrade list-markets \
    --config /freqtrade/$CONFIG_FILE \
    --print-json > $TEMP_OUTPUT

if [ $? -ne 0 ]; then
    echo "Failed to fetch markets"
    rm $TEMP_OUTPUT
    exit 1
fi

# Move temp output to final location
mv $TEMP_OUTPUT $MARKETS_FILE

echo "Validating schema..."
# Check if whitelist exists to pass as prev-whitelist for drift check
PREV_WHITELIST_ARG=""
if [ -f "$WHITELIST_JSON" ]; then
    PREV_WHITELIST_ARG="--prev-whitelist $WHITELIST_JSON"
fi

set +e # Allow failure for validation step
python3 tools/validate_markets_schema.py \
    --markets "$MARKETS_FILE" \
    --env "$DELTA_ENV" \
    $PREV_WHITELIST_ARG \
    --out-report "$REPORT_FILE"

VALIDATION_EXIT_CODE=$?
set -e

if [ $VALIDATION_EXIT_CODE -eq 0 ]; then
    echo "Validation PASSED."

    echo "Generating whitelist..."
    python3 tools/generate_whitelist.py "$MARKETS_FILE" > "$WHITELIST_JSON"

    # Generate TXT list (symbols only)
    python3 -c "import json, sys; print('\n'.join(json.load(open('$WHITELIST_JSON'))['exchange']['pair_whitelist']))" > "$WHITELIST_TXT"

    echo "Whitelist updated at $WHITELIST_JSON"

    # Clean up old dumps (keep last 7)
    ls -t $REPORTS_DIR/markets_*.json | tail -n +8 | xargs -I {} rm -- {} 2>/dev/null || true

else
    echo "Validation FAILED (Exit Code: $VALIDATION_EXIT_CODE)."
    echo "Check report at $REPORT_FILE"
    echo "Whitelist NOT updated."
    # Exit with the validation error code to fail CI
    exit $VALIDATION_EXIT_CODE
fi

echo "Done."
