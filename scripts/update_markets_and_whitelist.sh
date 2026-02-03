#!/bin/bash
set -e

# Ensure root
cd "$(dirname "$0")/.."

# Load env for python tools
if [ -f .env ]; then
    export $(cat .env | xargs)
fi

DELTA_ENV=${DELTA_ENV:-india_testnet}
TIMESTAMP=$(date -u +"%Y%m%d_%H%M%S")
REPORTS_DIR="user_data/reports"
PAIRLISTS_DIR="user_data/pairlists"
MARKETS_FILE="$REPORTS_DIR/markets_${TIMESTAMP}.json"
SCHEMA_REPORT="$REPORTS_DIR/markets_schema_report_${TIMESTAMP}.md"

mkdir -p $REPORTS_DIR
mkdir -p $PAIRLISTS_DIR

# Find latest previous dump
PREV_DUMP=$(ls -t $REPORTS_DIR/markets_*.json 2>/dev/null | head -n 1 || echo "")

echo "Fetching markets for $DELTA_ENV..."

# Use config to fetch markets. We use dryrun config.
# Ensure we capture stdout clean
docker compose run --rm freqtrade list-markets \
    --config user_data/configs/config.delta.dryrun.json \
    --print-json > "$MARKETS_FILE"

# Validate JSON content
if [ ! -s "$MARKETS_FILE" ]; then
    echo "FAIL: Markets file is empty"
    rm "$MARKETS_FILE"
    exit 1
fi

echo "Validating schema..."
python3 tools/validate_markets_schema.py "$MARKETS_FILE" "$PREV_DUMP" "$SCHEMA_REPORT"

echo "Generating whitelist..."
WHITELIST_JSON="$PAIRLISTS_DIR/whitelist.delta.json"
WHITELIST_TXT="$PAIRLISTS_DIR/whitelist.delta.txt"

python3 tools/generate_whitelist.py "$MARKETS_FILE" > "$WHITELIST_JSON"

# Generate TXT list (symbols only)
grep -o '"[^"]*:[^"]*"' "$WHITELIST_JSON" | tr -d '"' > "$WHITELIST_TXT"

echo "Whitelist updated at $WHITELIST_JSON"

# Drift Report (Diff)
DIFF_FILE="$REPORTS_DIR/whitelist_diff_${TIMESTAMP}.md"
echo "# Whitelist Drift Report" > $DIFF_FILE
echo "Date: $TIMESTAMP" >> $DIFF_FILE
echo "Env: $DELTA_ENV" >> $DIFF_FILE
echo "Previous: $PREV_DUMP" >> $DIFF_FILE
echo "Current: $MARKETS_FILE" >> $DIFF_FILE
echo "" >> $DIFF_FILE

if [ -n "$PREV_DUMP" ]; then
    # Generate diff of symbols
    # Helper to extract symbols
    extract_syms() {
        python3 -c "import json, sys; d=json.load(open('$1')); m=d['markets'] if 'markets' in d else d; print('\n'.join(sorted([x['symbol'] for x in m])))"
    }

    echo "## Changes" >> $DIFF_FILE
    echo "\`\`\`diff" >> $DIFF_FILE
    diff -u <(extract_syms "$PREV_DUMP") <(extract_syms "$MARKETS_FILE") >> $DIFF_FILE || true
    echo "\`\`\`" >> $DIFF_FILE
else
    echo "No previous dump for diff." >> $DIFF_FILE
fi

# Clean up old dumps (keep last 7)
ls -t $REPORTS_DIR/markets_*.json | tail -n +8 | xargs -I {} rm -- {} 2>/dev/null || true

echo "Done."
