#!/bin/bash
set -e

# Ensure root
cd "$(dirname "$0")/.."

# Load .env if exists
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

DELTA_ENV=${DELTA_ENV:-india_testnet}
TIMESTAMP=$(date -u +"%Y%m%d_%H%M%S")
REPORTS_DIR="user_data/reports"
PAIRLISTS_DIR="user_data/pairlists"
MARKETS_FILE="$REPORTS_DIR/markets_${TIMESTAMP}.json"

mkdir -p $REPORTS_DIR
mkdir -p $PAIRLISTS_DIR

# Find latest previous dump
PREV_DUMP=$(ls -t $REPORTS_DIR/markets_*.json 2>/dev/null | head -n 1 || echo "")

echo "Fetching markets for $DELTA_ENV..."

# Use a temp file to capture output
TEMP_OUTPUT=$(mktemp)

# Run freqtrade list-markets
# We must ensure we use the correct config and env vars
# docker compose run passes env vars from shell/env file if mapped
# Use -T to avoid TTY issues in CI/scripts
docker compose run --rm -T freqtrade list-markets \
    --config /freqtrade/user_data/configs/config.delta.dryrun.json \
    --print-json > $TEMP_OUTPUT

# Check exit code
if [ $? -ne 0 ]; then
    echo "Failed to fetch markets"
    rm $TEMP_OUTPUT
    exit 1
fi

# Verify JSON validity using python
if ! python3 -c "import json, sys; json.load(sys.stdin)" < "$TEMP_OUTPUT"; then
    echo "Output is not valid JSON. Check logs."
    cat $TEMP_OUTPUT
    rm $TEMP_OUTPUT
    exit 1
fi

echo "Validating schema and drift..."
# validate_markets_schema.py writes report to reports/markets_schema_report_*.md
# and exits 2 on failure
if ! python3 tools/validate_markets_schema.py "$TEMP_OUTPUT" "$PREV_DUMP"; then
    echo "Schema/Drift Validation Failed!"
    rm $TEMP_OUTPUT
    exit 1
fi

# Move valid dump to final location
mv $TEMP_OUTPUT $MARKETS_FILE
echo "Markets saved to $MARKETS_FILE"

echo "Generating whitelist..."
WHITELIST_JSON="$PAIRLISTS_DIR/whitelist.delta.json"
PREV_WHITELIST_JSON="$PAIRLISTS_DIR/whitelist.delta.bak"

# Backup current whitelist for diff
if [ -f "$WHITELIST_JSON" ]; then
    cp "$WHITELIST_JSON" "$PREV_WHITELIST_JSON"
fi

# Generate new whitelist
python3 tools/generate_whitelist.py "$MARKETS_FILE" > "$WHITELIST_JSON"

# Generate TXT list (symbols only)
WHITELIST_TXT="$PAIRLISTS_DIR/whitelist.delta.txt"
grep -o '"[^"]*:[^"]*"' "$WHITELIST_JSON" | tr -d '"' > "$WHITELIST_TXT"

echo "Whitelist updated at $WHITELIST_JSON"
echo "Whitelist TXT updated at $WHITELIST_TXT"

# Whitelist Drift Report
if [ -f "$PREV_WHITELIST_JSON" ]; then
    DIFF_FILE="$REPORTS_DIR/whitelist_diff_${TIMESTAMP}.md"
    echo "# Whitelist Changes" > $DIFF_FILE
    echo "Date: $TIMESTAMP" >> $DIFF_FILE

    # Extract pairs for diff using python
    echo "## Changes" >> $DIFF_FILE
    python3 -c "
import json, sys
try:
    with open('$PREV_WHITELIST_JSON') as f: old = set(json.load(f)['exchange']['pair_whitelist'])
except: old = set()
try:
    with open('$WHITELIST_JSON') as f: new = set(json.load(f)['exchange']['pair_whitelist'])
except: new = set()
added = sorted(list(new - old))
removed = sorted(list(old - new))
if added:
    print('### Added')
    for p in added: print(f'- {p}')
if removed:
    print('### Removed')
    for p in removed: print(f'- {p}')
if not added and not removed:
    print('No changes.')
" >> $DIFF_FILE

    echo "Report written to $DIFF_FILE"

    # Clean up bak
    rm "$PREV_WHITELIST_JSON"
fi

# Clean up old dumps (keep last 7)
ls -t $REPORTS_DIR/markets_*.json | tail -n +8 | xargs -I {} rm -- {} 2>/dev/null || true
ls -t $REPORTS_DIR/markets_schema_report_*.md | tail -n +8 | xargs -I {} rm -- {} 2>/dev/null || true
ls -t $REPORTS_DIR/whitelist_diff_*.md | tail -n +8 | xargs -I {} rm -- {} 2>/dev/null || true

echo "Done."
