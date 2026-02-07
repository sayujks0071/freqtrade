#!/bin/bash
set -e

# Ensure root
cd "$(dirname "$0")/.."

# Load environment
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

DELTA_ENV=${DELTA_ENV:-india_testnet}
TIMESTAMP=$(date -u +"%Y%m%d_%H%M%S")
REPORTS_DIR="user_data/reports"
PAIRLISTS_DIR="user_data/pairlists"
MARKETS_FILE="$REPORTS_DIR/markets_${TIMESTAMP}.json"
VALIDATION_REPORT="$REPORTS_DIR/markets_schema_report_${TIMESTAMP}.md"
PREV_WHITELIST="$PAIRLISTS_DIR/whitelist.delta.json"

mkdir -p $REPORTS_DIR
mkdir -p $PAIRLISTS_DIR

echo "Fetching markets for $DELTA_ENV..."

# Use a temporary file for the docker output
TEMP_OUTPUT=$(mktemp)

# Command to fetch markets.
# We ensure we use the correct config (dryrun usually has credentials/exchange setup)
# We assume 'config.delta.dryrun.json' exists and is valid.
CONFIG_FILE="user_data/configs/config.delta.dryrun.json"
if [ ! -f "$CONFIG_FILE" ]; then
    echo "Config file $CONFIG_FILE not found!"
    rm $TEMP_OUTPUT
    exit 1
fi

# Run freqtrade list-markets via Docker
docker compose run --rm freqtrade list-markets \
    --config /freqtrade/$CONFIG_FILE \
    --print-json > $TEMP_OUTPUT

# Check if docker command succeeded (basic check)
if [ $? -ne 0 ]; then
    echo "Failed to fetch markets (docker exit code)"
    rm $TEMP_OUTPUT
    exit 1
fi

# Move temp output to final location.
# In a real scenario, we might want to filter only valid JSON if logs are intermixed.
# For now, we assume --print-json is clean enough or the validator will catch JSON errors.
mv $TEMP_OUTPUT $MARKETS_FILE

echo "Validating schema..."
echo "Report will be at: $VALIDATION_REPORT"

# Run validation
# We temporarily disable 'set -e' to capture exit code cleanly without immediate abort
set +e
python3 tools/validate_markets_schema.py \
    --markets "$MARKETS_FILE" \
    --env "$DELTA_ENV" \
    --prev-whitelist "$PREV_WHITELIST" \
    --out-report "$VALIDATION_REPORT"

VALIDATOR_EXIT_CODE=$?
set -e

if [ $VALIDATOR_EXIT_CODE -ne 0 ]; then
    echo "---------------------------------------------------"
    echo "❌ Validation FAILED (Exit Code: $VALIDATOR_EXIT_CODE)"
    echo "Report summary:"
    # Print first 20 lines of report to console
    head -n 20 "$VALIDATION_REPORT"
    echo "..."
    echo "---------------------------------------------------"
    echo "Aborting whitelist update."
    exit 1
fi

echo "✅ Validation passed."

echo "Generating whitelist..."
WHITELIST_JSON="$PAIRLISTS_DIR/whitelist.delta.json"
WHITELIST_TXT="$PAIRLISTS_DIR/whitelist.delta.txt"

# Assuming tools/generate_whitelist.py exists and works
# We pass the validated markets file
python3 tools/generate_whitelist.py "$MARKETS_FILE" > "$WHITELIST_JSON"

# Also generate TXT list (symbols only)
# Simple extraction: look for "Base/Quote:Settle" patterns
grep -o '"[^"]*:[^"]*"' "$WHITELIST_JSON" | tr -d '"' > "$WHITELIST_TXT"

echo "Whitelist updated at $WHITELIST_JSON"

# Clean up old dumps (keep last 7)
ls -t $REPORTS_DIR/markets_*.json | tail -n +8 | xargs -I {} rm -- {} 2>/dev/null || true
ls -t $REPORTS_DIR/markets_schema_report_*.md | tail -n +8 | xargs -I {} rm -- {} 2>/dev/null || true

echo "Done."
