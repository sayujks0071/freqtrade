#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$DIR/common.sh"

set -e

TIMESTAMP=$(date -u +"%Y%m%d_%H%M%S")
REPORTS_DIR="user_data/reports"
PAIRLISTS_DIR="user_data/pairlists"
MARKETS_FILE="$REPORTS_DIR/markets_${TIMESTAMP}.json"

mkdir -p $REPORTS_DIR
mkdir -p $PAIRLISTS_DIR

# Find latest previous dump for drift check
PREV_DUMP=$(ls -t $REPORTS_DIR/markets_*.json 2>/dev/null | head -n 1 || echo "")

echo "Fetching markets for $DELTA_ENV (Futures)..."

TEMP_OUTPUT=$(mktemp)

# Run freqtrade list-markets
# We capture stdout. Stderr goes to null to avoid log pollution.
docker compose run --rm freqtrade list-markets \
    --config /freqtrade/user_data/configs/config.delta.dryrun.json \
    --exchange delta \
    --trading-mode futures \
    --print-json > $TEMP_OUTPUT 2> /dev/null

# Check if successful (docker exit code)
if [ $? -ne 0 ]; then
    echo "Failed to fetch markets (Docker command failed)."
    rm $TEMP_OUTPUT
    exit 1
fi

# Verify it is valid JSON.
if ! python3 -m json.tool $TEMP_OUTPUT >/dev/null 2>&1; then
    echo "Failed to fetch valid JSON markets. Output:"
    cat $TEMP_OUTPUT
    rm $TEMP_OUTPUT
    exit 1
fi

mv $TEMP_OUTPUT $MARKETS_FILE
echo "Markets saved to $MARKETS_FILE"

echo "Validating schema..."
python3 tools/validate_markets_schema.py "$MARKETS_FILE" "$PREV_DUMP"

echo "Generating whitelist..."
WHITELIST_JSON="$PAIRLISTS_DIR/whitelist.delta.json"
WHITELIST_TXT="$PAIRLISTS_DIR/whitelist.delta.txt"

python3 tools/generate_whitelist.py "$MARKETS_FILE" > "$WHITELIST_JSON"

# Text version
grep -o '"[^"]*:[^"]*"' "$WHITELIST_JSON" | tr -d '"' > "$WHITELIST_TXT"

echo "Whitelist updated at $WHITELIST_JSON"
