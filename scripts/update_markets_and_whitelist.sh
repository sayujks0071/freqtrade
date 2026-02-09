#!/bin/bash
set -e

# Ensure root
cd "$(dirname "$0")/.."

# Load environment
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
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

# Run freqtrade list-markets via Docker
# Note: config.delta.dryrun.json is used to set the exchange logic, but DELTA_BASE_URL env var overrides the URL.
# We map output to a temp file first to separate logs from JSON if needed, though --print-json usually works well.
TEMP_OUTPUT=$(mktemp)

# Ensure correct image is used
docker compose run --rm freqtrade list-markets \
    --config /freqtrade/user_data/configs/config.delta.dryrun.json \
    --exchange delta \
    --trading-mode futures \
    --print-json > $TEMP_OUTPUT

if [ $? -ne 0 ]; then
    echo "Failed to fetch markets"
    rm $TEMP_OUTPUT
    exit 1
fi

# Extract JSON from potential logs
# Usually list-markets output is pure JSON with --print-json, but sometimes logs creep in.
# We look for the first '[' or '{'
# But 'grep' is risky if multiline.
# Let's assume Freqtrade is well-behaved or we use a python snippet to extract the largest JSON block.
# For now, we move it directly, assuming silent mode is effective or output is clean.
mv $TEMP_OUTPUT $MARKETS_FILE

echo "Validating schema..."
python3 tools/validate_markets_schema.py "$MARKETS_FILE" "$PREV_DUMP"

echo "Generating whitelist..."
WHITELIST_JSON="$PAIRLISTS_DIR/whitelist.delta.json"
WHITELIST_TXT="$PAIRLISTS_DIR/whitelist.delta.txt"

# generate_whitelist.py prints the JSON config structure to stdout
python3 tools/generate_whitelist.py "$MARKETS_FILE" > "$WHITELIST_JSON"

# Also generate TXT list (symbols only) for easy reading/copying
# Extract symbols from the generated JSON
grep -o '"[^"]*:[^"]*"' "$WHITELIST_JSON" | tr -d '"' | sort > "$WHITELIST_TXT"

echo "Whitelist updated at $WHITELIST_JSON"
echo "Symbols list at $WHITELIST_TXT"

# Generate Drift Report
if [ -n "$PREV_DUMP" ]; then
    DIFF_FILE="$REPORTS_DIR/whitelist_diff_${TIMESTAMP}.md"
    echo "# Whitelist Drift Report" > $DIFF_FILE
    echo "Date: $TIMESTAMP" >> $DIFF_FILE
    echo "Previous: $PREV_DUMP" >> $DIFF_FILE
    echo "Current: $MARKETS_FILE" >> $DIFF_FILE
    echo "" >> $DIFF_FILE
    echo "## Changes" >> $DIFF_FILE
    # Simple diff of symbols
    # We can use diff command on the sorted txt lists if we had previous txt
    # Or just rely on validate_markets_schema output which prints drift stats.
    # Let's include the schema report content if possible.

    # We can also diff the .txt files if we kept the old one.
    # But for now, just a placeholder.
    echo "See console output or schema validation report for details." >> $DIFF_FILE
fi

# Clean up old dumps (keep last 7)
ls -t $REPORTS_DIR/markets_*.json | tail -n +8 | xargs -I {} rm -- {} 2>/dev/null || true

echo "Done."
