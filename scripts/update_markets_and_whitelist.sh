#!/bin/bash
set -e

# Ensure root
cd "$(dirname "$0")/.."

# Load env
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

# Use a temp file for docker output
TEMP_OUTPUT=$(mktemp)

# Run list-markets.
# We rely on config.delta.dryrun.json for exchange params, but override if needed.
# We must capture ONLY the JSON output.
docker compose run --rm freqtrade list-markets \
    --config /freqtrade/user_data/configs/config.delta.dryrun.json \
    --print-json > $TEMP_OUTPUT

# Check if successful
if [ $? -ne 0 ]; then
    echo "Failed to fetch markets"
    rm $TEMP_OUTPUT
    exit 1
fi

# Freqtrade might output logs before the JSON.
# We'll use a python script to extract the list.
python3 -c "
import sys, json, re
try:
    content = open('$TEMP_OUTPUT').read()
    # Find list start and end
    match = re.search(r'\[.*\]', content, re.DOTALL)
    if match:
        print(match.group(0))
    else:
        # Maybe it's a dict '{\"markets\": ...}'
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            print(match.group(0))
        else:
            sys.exit(1)
except Exception:
    sys.exit(1)
" > $MARKETS_FILE

if [ ! -s "$MARKETS_FILE" ]; then
    echo "Error: Failed to parse valid JSON from output."
    cat $TEMP_OUTPUT
    rm $TEMP_OUTPUT
    rm $MARKETS_FILE
    exit 1
fi
rm $TEMP_OUTPUT

echo "Validating schema..."
if python3 tools/validate_markets_schema.py "$MARKETS_FILE" "$PREV_DUMP"; then
    echo "Validation Passed."
else
    echo "Validation Failed. Aborting whitelist update."
    # We exit 1 here so CI fails
    exit 1
fi

echo "Generating whitelist..."
python3 tools/generate_whitelist.py "$MARKETS_FILE"

# Drift Report (Diff)
if [ -n "$PREV_DUMP" ]; then
    DIFF_FILE="$REPORTS_DIR/whitelist_diff_${TIMESTAMP}.md"
    echo "# Whitelist Drift Report" > $DIFF_FILE
    echo "Date: $TIMESTAMP" >> $DIFF_FILE
    echo "Previous: $PREV_DUMP" >> $DIFF_FILE
    echo "Current: $MARKETS_FILE" >> $DIFF_FILE
    echo "" >> $DIFF_FILE
    echo "## Changes" >> $DIFF_FILE

    # Generate simple diff of whitelist TXT
    PREV_WL_TXT="$PAIRLISTS_DIR/whitelist.delta.txt" # This is the currently active one
    NEW_WL_TXT="$PAIRLISTS_DIR/whitelist.delta.txt" # This was just overwritten, wait.

    # We overwrote the whitelist.txt. Ideally we should have kept the old one for diffing.
    # But generate_whitelist just overwrites.
    # We can rely on git to show the diff if we commit it.

    # Let's try to diff the JSONs directly using python for the report
    python3 -c "
import json
try:
    with open('$PREV_DUMP') as f: p = {m['symbol'] for m in json.load(f)}
    with open('$MARKETS_FILE') as f: c = {m['symbol'] for m in json.load(f)}
    added = c - p
    removed = p - c
    print('### Added')
    for x in sorted(added): print(f'- {x}')
    print('\n### Removed')
    for x in sorted(removed): print(f'- {x}')
except:
    print('Could not generate detailed diff.')
" >> $DIFF_FILE

    echo "Drift report saved to $DIFF_FILE"
fi

# Clean up old dumps (keep last 7)
ls -t $REPORTS_DIR/markets_*.json | tail -n +8 | xargs -I {} rm -- {} 2>/dev/null || true

echo "Done."
