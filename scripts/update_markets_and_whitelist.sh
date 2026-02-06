#!/bin/bash
set -e
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$DIR/common.sh"

DELTA_ENV=${DELTA_ENV:-india_testnet}
TIMESTAMP=$(date -u +"%Y%m%d_%H%M%S")
REPORTS_DIR="user_data/reports"
PAIRLISTS_DIR="user_data/pairlists"
MARKETS_FILE="$REPORTS_DIR/markets_${TIMESTAMP}.json"

mkdir -p $REPORTS_DIR
mkdir -p $PAIRLISTS_DIR

# Find latest previous dump for drift check
PREV_DUMP=$(ls -t $REPORTS_DIR/markets_*.json 2>/dev/null | head -n 1 || echo "")

echo "Fetching markets for $DELTA_ENV..."

# Use temp file for raw output
TEMP_RAW=$(mktemp)

# Ensure docker image is available
docker compose pull freqtrade >/dev/null 2>&1 || true

docker compose run --rm freqtrade list-markets \
    --config /freqtrade/user_data/configs/config.delta.dryrun.json \
    --print-json > "$TEMP_RAW"

if [ $? -ne 0 ]; then
    echo "Failed to run list-markets"
    rm "$TEMP_RAW"
    exit 1
fi

# Parse JSON with python
python3 -c "
import sys, json, re
try:
    with open('$TEMP_RAW', 'r') as f:
        content = f.read()
    match = re.search(r'\[.*\]', content, re.DOTALL)
    if not match: match = re.search(r'\{.*\}', content, re.DOTALL)
    if match:
        data = json.loads(match.group(0))
        if isinstance(data, dict):
            if 'markets' in data: data = data['markets']
            elif 'pairs' in data: data = data['pairs']
        with open('$MARKETS_FILE', 'w') as f:
            json.dump(data, f, indent=4)
    else:
        print('No JSON found in output')
        sys.exit(1)
except Exception as e:
    print(e)
    sys.exit(1)
"

if [ $? -ne 0 ]; then
    echo "Failed to parse markets JSON"
    cat "$TEMP_RAW"
    rm "$TEMP_RAW"
    exit 1
fi
rm "$TEMP_RAW"

echo "Markets saved to $MARKETS_FILE"

# Validate Schema & Drift
echo "Validating schema..."
python3 tools/validate_markets_schema.py "$MARKETS_FILE" "$PREV_DUMP"

if [ $? -ne 0 ]; then
    echo "Schema validation failed!"
    exit 1
fi

# Generate Whitelist
echo "Generating whitelist..."
WHITELIST_JSON="$PAIRLISTS_DIR/whitelist.delta.json"
WHITELIST_TXT="$PAIRLISTS_DIR/whitelist.delta.txt"

python3 tools/generate_whitelist.py "$MARKETS_FILE" json > "$WHITELIST_JSON"
python3 tools/generate_whitelist.py "$MARKETS_FILE" text > "$WHITELIST_TXT"

echo "Whitelist updated: $WHITELIST_JSON"

# Drift Report (Diff)
if [ -n "$PREV_DUMP" ]; then
    DIFF_FILE="$REPORTS_DIR/whitelist_diff_${TIMESTAMP}.md"
    echo "# Whitelist Drift Report" > $DIFF_FILE
    echo "Date: $TIMESTAMP" >> $DIFF_FILE
    echo "Previous: $(basename $PREV_DUMP)" >> $DIFF_FILE
    echo "Current: $(basename $MARKETS_FILE)" >> $DIFF_FILE
    echo "" >> $DIFF_FILE
    echo "## Added Pairs" >> $DIFF_FILE
    python3 -c "
import json
try:
    with open('$PREV_DUMP') as f:
        d = json.load(f)
        old = set(m['symbol'] for m in (d['markets'] if isinstance(d, dict) and 'markets' in d else d))
    with open('$MARKETS_FILE') as f:
        d = json.load(f)
        new = set(m['symbol'] for m in (d['markets'] if isinstance(d, dict) and 'markets' in d else d))
    added = sorted(list(new - old))
    removed = sorted(list(old - new))
    for p in added: print(f'- {p}')
    print('\n## Removed Pairs')
    for p in removed: print(f'- {p}')
except: pass
" >> $DIFF_FILE
    echo "Diff report saved to $DIFF_FILE"
fi

# Clean up old dumps (keep last 7)
ls -t $REPORTS_DIR/markets_*.json 2>/dev/null | tail -n +8 | xargs -I {} rm -- {} 2>/dev/null || true

echo "Market Refresh Complete."
