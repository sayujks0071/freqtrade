#!/bin/bash
set -e
cd "$(dirname "$0")/.."

source scripts/common.sh

echo "Updating Delta Markets & Whitelist for $DELTA_ENV..."
echo "Filter Mode: $FILTER_MODE"

# 1. Fetch Markets
TIMESTAMP=$(date -u +"%Y%m%d_%H%M%S")
REPORT_DIR="user_data/reports"
mkdir -p "$REPORT_DIR"
MARKETS_FILE="$REPORT_DIR/markets_${TIMESTAMP}.json"

echo "Fetching markets..."
TEMP_OUTPUT=$(mktemp)
# Use docker to ensure ccxt compatibility
# Use dryrun config
docker compose run --rm freqtrade list-markets \
    --config /freqtrade/user_data/configs/config.delta.dryrun.json \
    --exchange delta \
    --trading-mode futures \
    --print-json > "$TEMP_OUTPUT" 2>/dev/null || true

if [ ! -s "$TEMP_OUTPUT" ]; then
    echo "ERROR: Failed to fetch markets."
    rm "$TEMP_OUTPUT"
    exit 1
fi

# Basic check if it's JSON
if ! grep -q "\[" "$TEMP_OUTPUT"; then
    echo "ERROR: Output does not look like JSON list."
    cat "$TEMP_OUTPUT"
    rm "$TEMP_OUTPUT"
    exit 1
fi

mv "$TEMP_OUTPUT" "$MARKETS_FILE"
echo "Markets saved to $MARKETS_FILE"

# 2. Validate Schema & Drift
echo "Validating schema and drift..."
# Find LATEST previous dump (before this one)
PREV_DUMP=$(ls -t "$REPORT_DIR"/markets_*.json 2>/dev/null | grep -v "$TIMESTAMP" | head -n 1 || echo "")

# This tool will exit 2 on failure
python3 tools/validate_markets_schema.py "$MARKETS_FILE" $PREV_DUMP

# 3. Generate Whitelist
echo "Generating whitelist..."
WHITELIST_DIR="user_data/pairlists"
mkdir -p "$WHITELIST_DIR"
WHITELIST_JSON="$WHITELIST_DIR/whitelist.delta.json"
WHITELIST_TXT="$WHITELIST_DIR/whitelist.delta.txt"

# Generate JSON config snippet
python3 tools/generate_whitelist.py "$MARKETS_FILE" > "$WHITELIST_JSON"
echo "Whitelist JSON updated: $WHITELIST_JSON"

# Generate TXT list (symbols only)
python3 -c "import json; print('\n'.join(json.load(open('$WHITELIST_JSON'))['exchange']['pair_whitelist']))" > "$WHITELIST_TXT"
echo "Whitelist TXT updated: $WHITELIST_TXT"

# 4. Generate Drift Report (Markdown)
if [ -n "$PREV_DUMP" ]; then
    DIFF_FILE="$REPORT_DIR/whitelist_diff_${TIMESTAMP}.md"
    echo "# Whitelist Drift Report" > "$DIFF_FILE"
    echo "Date: $TIMESTAMP" >> "$DIFF_FILE"
    echo "Previous Dump: $PREV_DUMP" >> "$DIFF_FILE"
    echo "Current Dump: $MARKETS_FILE" >> "$DIFF_FILE"
    echo "" >> "$DIFF_FILE"

    CURR_WL_TXT=$(mktemp)
    cat "$WHITELIST_TXT" | sort > "$CURR_WL_TXT"

    PREV_WL_TXT=$(mktemp)
    # Generate whitelist from previous dump using same filter settings
    python3 tools/generate_whitelist.py "$PREV_DUMP" | python3 -c "import json, sys; print('\n'.join(json.load(sys.stdin)['exchange']['pair_whitelist']))" | sort > "$PREV_WL_TXT"

    echo "## Added Pairs" >> "$DIFF_FILE"
    # comm -13: lines unique to file2 (added)
    comm -13 "$PREV_WL_TXT" "$CURR_WL_TXT" | sed 's/^/- /' >> "$DIFF_FILE"

    echo "" >> "$DIFF_FILE"
    echo "## Removed Pairs" >> "$DIFF_FILE"
    # comm -23: lines unique to file1 (removed)
    comm -23 "$PREV_WL_TXT" "$CURR_WL_TXT" | sed 's/^/- /' >> "$DIFF_FILE"

    rm "$PREV_WL_TXT" "$CURR_WL_TXT"
    echo "Drift report generated: $DIFF_FILE"
fi

# 5. Cleanup Old Dumps
echo "Cleaning up old dumps..."
# Keep last 7 json files
ls -t "$REPORT_DIR"/markets_*.json 2>/dev/null | tail -n +8 | xargs -I {} rm -- {} 2>/dev/null || true
# Keep last 7 reports
ls -t "$REPORT_DIR"/markets_schema_report_*.md 2>/dev/null | tail -n +8 | xargs -I {} rm -- {} 2>/dev/null || true
ls -t "$REPORT_DIR"/whitelist_diff_*.md 2>/dev/null | tail -n +8 | xargs -I {} rm -- {} 2>/dev/null || true

echo "Update Complete."
