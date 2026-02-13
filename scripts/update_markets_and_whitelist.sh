#!/bin/bash
set -e

# Ensure root
cd "$(dirname "$0")/.."

DELTA_ENV=${DELTA_ENV:-india_testnet}
TIMESTAMP=$(date -u +"%Y%m%d_%H%M%S")
REPORTS_DIR="user_data/reports"
PAIRLISTS_DIR="user_data/pairlists"

mkdir -p $REPORTS_DIR
mkdir -p $PAIRLISTS_DIR

echo "Fetching markets for $DELTA_ENV..."

# Use temp files
TEMP_MARKETS=$(mktemp)
TEMP_WHITELIST=$(mktemp)
REPORT_FILE="$REPORTS_DIR/markets_schema_report_${TIMESTAMP}.md"

# Load env vars
if [ -f .env ]; then
    export $(cat .env | xargs)
fi

# Fetch Markets
# We explicitly set config to delta dryrun (or any config with exchange delta)
# or just pass args.
# We need to ensure we connect to the right exchange environment.
# Since config.delta.dryrun.json has exchange settings, we use it.

# Note: In strict CI environment, ensure secrets are available.
# But list-markets only needs public API usually.

docker compose run --rm freqtrade list-markets \
    --config /freqtrade/user_data/configs/config.delta.dryrun.json \
    --print-json > $TEMP_MARKETS

if [ ! -s $TEMP_MARKETS ]; then
    echo "Failed to fetch markets or empty output"
    rm $TEMP_MARKETS $TEMP_WHITELIST
    exit 1
fi

# Generate Candidate Whitelist
# We must generate it to validate it.
python3 tools/generate_whitelist.py "$TEMP_MARKETS" > "$TEMP_WHITELIST"

# Previous Whitelist
PREV_WHITELIST="$PAIRLISTS_DIR/whitelist.delta.json"

echo "Validating schema..."
# Run validator. If it fails, exit code will be non-zero.
# We use ! to invert exit code so if valid fails (non-zero), if block executes.
if ! python3 tools/validate_markets_schema.py \
    --markets "$TEMP_MARKETS" \
    --candidate-whitelist "$TEMP_WHITELIST" \
    --prev-whitelist "$PREV_WHITELIST" \
    --env "$DELTA_ENV" \
    --out-report "$REPORT_FILE"; then

    echo "Validation failed! See report at $REPORT_FILE"

    # Move failed dump to reports so it's uploaded as artifact
    mv $TEMP_MARKETS "$REPORTS_DIR/markets_failed_${TIMESTAMP}.json"
    rm $TEMP_WHITELIST

    # Validation failed, exit with error
    exit 1
fi

# Success
echo "Validation passed."
MARKETS_FILE="$REPORTS_DIR/markets_${TIMESTAMP}.json"
mv $TEMP_MARKETS $MARKETS_FILE

# Update Whitelist
mv $TEMP_WHITELIST "$PAIRLISTS_DIR/whitelist.delta.json"

# Generate TXT list (symbols only)
grep -o '"[^"]*:[^"]*"' "$PAIRLISTS_DIR/whitelist.delta.json" | tr -d '"' > "$PAIRLISTS_DIR/whitelist.delta.txt"

echo "Whitelist updated at $PAIRLISTS_DIR/whitelist.delta.json"

# Clean up old dumps (keep last 7)
ls -t $REPORTS_DIR/markets_*.json 2>/dev/null | tail -n +8 | xargs -I {} rm -- {} 2>/dev/null || true

echo "Done."
