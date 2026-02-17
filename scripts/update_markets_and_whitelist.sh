#!/bin/bash
set -e

# Ensure root
cd "$(dirname "$0")/.."

# Source common environment setup if available, ensuring env vars are loaded
if [ -f "scripts/common.sh" ]; then
    source scripts/common.sh
else
    # Fallback if common.sh missing
    if [ -f .env ]; then
        export $(grep -v '^#' .env | xargs)
    fi
    DELTA_ENV=${DELTA_ENV:-india_testnet}
fi

TIMESTAMP=$(date -u +"%Y%m%d_%H%M%S")
REPORTS_DIR="user_data/reports"
PAIRLISTS_DIR="user_data/pairlists"
MARKETS_FILE="$REPORTS_DIR/markets_${TIMESTAMP}.json"
WHITELIST_JSON="$PAIRLISTS_DIR/whitelist.delta.json"
REPORT_FILE="$REPORTS_DIR/markets_schema_report_${TIMESTAMP}.md"

mkdir -p $REPORTS_DIR
mkdir -p $PAIRLISTS_DIR

echo "Fetching markets for $DELTA_ENV..."

# Use a temporary file for the raw output
TEMP_OUTPUT=$(mktemp)

# Command to fetch markets.
# We use the dryrun config which should have the exchange configured.
docker compose run --rm freqtrade list-markets \
    --config /freqtrade/user_data/configs/config.delta.dryrun.json \
    --print-json > $TEMP_OUTPUT

# Check if docker command succeeded (basic check)
if [ $? -ne 0 ]; then
    echo "Failed to fetch markets"
    rm $TEMP_OUTPUT
    exit 1
fi

echo "Validating schema..."
# Run the Python validator
# We allow it to fail (set +e) to handle the exit code manually
set +e
python3 tools/validate_markets_schema.py \
    --markets "$TEMP_OUTPUT" \
    --prev-whitelist "$WHITELIST_JSON" \
    --env "$DELTA_ENV" \
    --out-report "$REPORT_FILE"

VALID_EXIT_CODE=$?
set -e

if [ $VALID_EXIT_CODE -eq 0 ]; then
    echo "Validation PASS."

    # Move valid dump to final location
    mv "$TEMP_OUTPUT" "$MARKETS_FILE"

    echo "Generating whitelist..."

    python3 tools/generate_whitelist.py "$MARKETS_FILE" > "$WHITELIST_JSON"

    # Also generate TXT list (symbols only)
    WHITELIST_TXT="$PAIRLISTS_DIR/whitelist.delta.txt"
    grep -o '"[^"]*:[^"]*"' "$WHITELIST_JSON" | tr -d '"' > "$WHITELIST_TXT"

    echo "Whitelist updated at $WHITELIST_JSON"

    # Clean up old dumps (keep last 7)
    ls -t $REPORTS_DIR/markets_*.json 2>/dev/null | tail -n +8 | xargs -I {} rm -- {} 2>/dev/null || true

    echo "Done."
else
    echo "Validation FAIL. See report at $REPORT_FILE"

    # Save the failed dump for debugging
    FAILED_DUMP="$REPORTS_DIR/markets_${TIMESTAMP}_FAILED.json"
    mv "$TEMP_OUTPUT" "$FAILED_DUMP"
    echo "Failed dump saved to $FAILED_DUMP"

    exit 1
fi
