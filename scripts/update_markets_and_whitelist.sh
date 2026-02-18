#!/bin/bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$DIR/common.sh"

TIMESTAMP=$(date -u +"%Y%m%d_%H%M%S")
REPORTS_DIR="user_data/reports"
PAIRLISTS_DIR="user_data/pairlists"
MARKETS_FILE="$REPORTS_DIR/markets_${TIMESTAMP}.json"

mkdir -p $REPORTS_DIR
mkdir -p $PAIRLISTS_DIR

# Find latest previous dump for drift check
PREV_DUMP=$(ls -t $REPORTS_DIR/markets_*.json 2>/dev/null | head -n 1 || echo "")

echo "Fetching markets for $DELTA_ENV..."

# Use a temp file to capture output
TEMP_OUTPUT=$(mktemp)

# Run freqtrade list-markets
# We need to make sure we use the correct config for credentials/urls
# We use config.delta.dryrun.json as it should have exchange settings
docker compose run --rm freqtrade list-markets \
    --config /freqtrade/user_data/configs/config.delta.dryrun.json \
    --print-json > $TEMP_OUTPUT

# Check exit code
if [ $? -ne 0 ]; then
    echo "Failed to fetch markets"
    rm $TEMP_OUTPUT
    exit 1
fi

# Move to final location
mv $TEMP_OUTPUT $MARKETS_FILE

echo "Validating schema..."
# Pass previous dump if it exists
if [ -z "$PREV_DUMP" ]; then
    python3 tools/validate_markets_schema.py "$MARKETS_FILE"
else
    python3 tools/validate_markets_schema.py "$MARKETS_FILE" "$PREV_DUMP"
fi

echo "Generating whitelist..."
WHITELIST_JSON="$PAIRLISTS_DIR/whitelist.delta.json"
WHITELIST_TXT="$PAIRLISTS_DIR/whitelist.delta.txt"

python3 tools/generate_whitelist.py "$MARKETS_FILE" > "$WHITELIST_JSON"

# Generate TXT list (symbols only)
python3 -c "import json, sys; print('\n'.join(json.load(open('$WHITELIST_JSON'))['exchange']['pair_whitelist']))" > "$WHITELIST_TXT"

echo "Whitelist updated at $WHITELIST_JSON"

# Clean up old dumps (keep last 7)
ls -t $REPORTS_DIR/markets_*.json | tail -n +8 | xargs -I {} rm -- {} 2>/dev/null || true

echo "Done."
