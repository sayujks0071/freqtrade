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
WHITELIST_JSON="$PAIRLISTS_DIR/whitelist.delta.json"
WHITELIST_TXT="$PAIRLISTS_DIR/whitelist.delta.txt"

mkdir -p $REPORTS_DIR
mkdir -p $PAIRLISTS_DIR

echo "Fetching markets for $DELTA_ENV..."

# Load env
if [ -f .env ]; then
    export $(cat .env | xargs)
fi

# Fetch markets
TEMP_OUTPUT=$(mktemp)
# We use docker compose to run freqtrade list-markets.
# Ensure we map necessary volumes/configs if not already handled by compose.
docker compose run --rm freqtrade list-markets \
    --config /freqtrade/user_data/configs/config.delta.dryrun.json \
    --print-json > $TEMP_OUTPUT

if [ $? -ne 0 ]; then
    echo "Failed to fetch markets"
    rm $TEMP_OUTPUT
    exit 1
fi

mv $TEMP_OUTPUT $MARKETS_FILE

echo "Validating schema..."

# Prepare validator arguments
VALIDATOR_ARGS=(--markets "$MARKETS_FILE" --env "$DELTA_ENV" --out-report "$REPORT_FILE")
if [ -f "$WHITELIST_JSON" ]; then
    VALIDATOR_ARGS+=(--prev-whitelist "$WHITELIST_JSON")
fi

# Run validator
# We allow it to fail, so we capture exit code
set +e
python3 tools/validate_markets_schema.py "${VALIDATOR_ARGS[@]}"
VALIDATOR_EXIT=$?
set -e

if [ $VALIDATOR_EXIT -ne 0 ]; then
    echo "ERROR: Validation failed! See $REPORT_FILE for details."
    echo "Whitelist will NOT be updated."
    exit 1
fi

echo "Validation passed. Regenerating whitelist..."

python3 tools/generate_whitelist.py "$MARKETS_FILE" > "$WHITELIST_JSON"

# Also generate TXT list (symbols only)
# Extract strings looking like symbols from JSON structure
grep -o '"[^"]*:[^"]*"' "$WHITELIST_JSON" | tr -d '"' > "$WHITELIST_TXT"

echo "Whitelist updated at $WHITELIST_JSON"

# Clean up old dumps (keep last 7)
ls -t $REPORTS_DIR/markets_*.json 2>/dev/null | tail -n +8 | xargs -I {} rm -- {} 2>/dev/null || true
ls -t $REPORTS_DIR/markets_schema_report_*.md 2>/dev/null | tail -n +8 | xargs -I {} rm -- {} 2>/dev/null || true

echo "Done."
