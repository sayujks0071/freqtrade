#!/bin/bash
set -e

# Ensure we are in the root
cd "$(dirname "$0")/.."

DELTA_ENV=${DELTA_ENV:-india_testnet}
TIMESTAMP=$(date -u +"%Y%m%d_%H%M%S")
REPORTS_DIR="user_data/reports"
PAIRLISTS_DIR="user_data/pairlists"
MARKETS_FILE="$REPORTS_DIR/markets_${TIMESTAMP}.json"

mkdir -p $REPORTS_DIR
mkdir -p $PAIRLISTS_DIR

# Find latest previous dump (for drift comparison)
PREV_DUMP=$(ls -t $REPORTS_DIR/markets_*.json 2>/dev/null | head -n 1 || echo "")

echo "Fetching markets for $DELTA_ENV..."

# Use a temporary file for the docker output
TEMP_OUTPUT=$(mktemp)

# Run freqtrade list-markets via Docker
# Note: We use dryrun config as it should have exchange settings capable of fetching markets
CONFIG_FILE="/freqtrade/user_data/configs/config.delta.dryrun.json"

docker compose run --rm freqtrade list-markets \
    --config "$CONFIG_FILE" \
    --exchange delta \
    --trading-mode futures \
    --print-json > $TEMP_OUTPUT

# Check if successful
if [ $? -ne 0 ]; then
    echo "Failed to fetch markets"
    rm $TEMP_OUTPUT
    exit 1
fi

# Move temp output to final location
mv $TEMP_OUTPUT $MARKETS_FILE

echo "Validating schema..."
python3 tools/validate_markets_schema.py "$MARKETS_FILE" "$PREV_DUMP"

echo "Generating whitelist..."
WHITELIST_JSON="$PAIRLISTS_DIR/whitelist.delta.json"
WHITELIST_TXT="$PAIRLISTS_DIR/whitelist.delta.txt"

python3 tools/generate_whitelist.py "$MARKETS_FILE" > "$WHITELIST_JSON"

# Also generate TXT list (symbols only)
grep -o '"[^"]*:[^"]*"' "$WHITELIST_JSON" | tr -d '"' > "$WHITELIST_TXT"

echo "Whitelist updated at $WHITELIST_JSON"

# Drift Report (Diff)
if [ -n "$PREV_DUMP" ]; then
    DIFF_FILE="$REPORTS_DIR/whitelist_diff_${TIMESTAMP}.md"
    echo "# Whitelist Drift Report" > $DIFF_FILE
    echo "Date: $TIMESTAMP" >> $DIFF_FILE
    echo "Previous: $PREV_DUMP" >> $DIFF_FILE
    echo "Current: $MARKETS_FILE" >> $DIFF_FILE
    echo "" >> $DIFF_FILE
    echo "## Changes" >> $DIFF_FILE

    # Python one-liner for diff logic could be better, but simple grep diff:
    echo "Check git diff or tools output for details." >> $DIFF_FILE
    echo "Generated via update script." >> $DIFF_FILE
fi

# Clean up old dumps (keep last 7)
ls -t $REPORTS_DIR/markets_*.json 2>/dev/null | tail -n +8 | xargs -I {} rm -- {} 2>/dev/null || true

echo "Done."
