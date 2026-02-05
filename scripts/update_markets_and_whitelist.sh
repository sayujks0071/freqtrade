#!/bin/bash
set -e

# Ensure root
cd "$(dirname "$0")/.."

# Load .env if present
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

DELTA_ENV=${DELTA_ENV:-india_testnet}
TIMESTAMP=$(date -u +"%Y%m%d_%H%M%S")
REPORTS_DIR="user_data/reports"
PAIRLISTS_DIR="user_data/pairlists"
MARKETS_FILE="$REPORTS_DIR/markets_${DELTA_ENV}_${TIMESTAMP}.json"

mkdir -p $REPORTS_DIR
mkdir -p $PAIRLISTS_DIR

# Find latest previous dump for drift check
PREV_DUMP=$(ls -t $REPORTS_DIR/markets_${DELTA_ENV}_*.json 2>/dev/null | head -n 1 || echo "")

echo "Fetching markets for $DELTA_ENV..."

# Use temp file for raw output to avoid partial writes or log noise
TEMP_OUTPUT=$(mktemp)

# Run freqtrade list-markets via Docker
# We use config.delta.dryrun.json as base config
docker compose run --rm freqtrade list-markets \
    --config /freqtrade/user_data/configs/config.delta.dryrun.json \
    --print-json > $TEMP_OUTPUT

# Check exit code
if [ $? -ne 0 ]; then
    echo "Failed to fetch markets via Docker"
    rm $TEMP_OUTPUT
    exit 1
fi

# Move to final location
mv $TEMP_OUTPUT $MARKETS_FILE
echo "Saved markets to $MARKETS_FILE"

echo "Validating schema..."
# validate_markets_schema.py <current> [previous]
python3 tools/validate_markets_schema.py "$MARKETS_FILE" "$PREV_DUMP"

echo "Generating whitelist..."
WHITELIST_JSON="$PAIRLISTS_DIR/whitelist.delta.json"
WHITELIST_ENV_JSON="$PAIRLISTS_DIR/whitelist.delta.${DELTA_ENV}.json"
WHITELIST_TXT="$PAIRLISTS_DIR/whitelist.delta.${DELTA_ENV}.txt"

# Generate JSON whitelist
python3 tools/generate_whitelist.py "$MARKETS_FILE" > "$WHITELIST_JSON"

# Copy to env specific file for backup/reference
cp "$WHITELIST_JSON" "$WHITELIST_ENV_JSON"

# Generate TXT list (symbols only)
grep -o '"[^"]*:[^"]*"' "$WHITELIST_JSON" | tr -d '"' > "$WHITELIST_TXT"

echo "Whitelist updated at $WHITELIST_JSON"

# Drift Report (Diff)
if [ -n "$PREV_DUMP" ]; then
    DIFF_FILE="$REPORTS_DIR/whitelist_diff_${TIMESTAMP}.md"
    echo "# Whitelist Drift Report" > $DIFF_FILE
    echo "Date: $TIMESTAMP" >> $DIFF_FILE
    echo "Env: $DELTA_ENV" >> $DIFF_FILE
    echo "Previous: $PREV_DUMP" >> $DIFF_FILE
    echo "Current: $MARKETS_FILE" >> $DIFF_FILE
    echo "" >> $DIFF_FILE
    echo "## Changes" >> $DIFF_FILE

    # Python script to generate diff stats
    python3 -c "
import json, sys
try:
    with open('$PREV_DUMP') as f:
        d = json.load(f)
        old = {m['symbol'] for m in (d.get('markets') if isinstance(d, dict) else d) if m.get('active')}
    with open('$MARKETS_FILE') as f:
        d = json.load(f)
        new = {m['symbol'] for m in (d.get('markets') if isinstance(d, dict) else d) if m.get('active')}

    added = new - old
    removed = old - new

    print(f'- Added: {len(added)}')
    for s in sorted(added): print(f'  + {s}')
    print(f'- Removed: {len(removed)}')
    for s in sorted(removed): print(f'  - {s}')
except Exception as e:
    print(f'Error calculating diff: {e}')
" >> $DIFF_FILE

    echo "Drift report generated at $DIFF_FILE"
fi

# Clean up old dumps (keep last 7)
ls -t $REPORTS_DIR/markets_${DELTA_ENV}_*.json | tail -n +8 | xargs -I {} rm -- {} 2>/dev/null || true

echo "Done."
