#!/bin/bash
set -e

# Ensure root
cd "$(dirname "$0")/.."

# Source common environment setup
source scripts/common.sh

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

# We use a temporary file for the docker output because of potential log noise
TEMP_OUTPUT=$(mktemp)

# Export CCXT config URLs for docker
export FREQTRADE__EXCHANGE__CCXT_CONFIG__URLS__API__public=$DELTA_BASE_URL
export FREQTRADE__EXCHANGE__CCXT_CONFIG__URLS__API__private=$DELTA_BASE_URL

echo "Using API URL: $DELTA_BASE_URL"

# Command to fetch markets.
docker compose run --rm freqtrade list-markets \
    --config /freqtrade/user_data/configs/config.delta.dryrun.json \
    --exchange delta --trading-mode futures \
    --print-json > $TEMP_OUTPUT

# Check if successful
if [ $? -ne 0 ]; then
    echo "Failed to fetch markets"
    rm $TEMP_OUTPUT
    exit 1
fi

# Attempt to extract JSON from the output (skip logs)
# Freqtrade usually outputs JSON last.
# We look for the first line starting with '[' or '{' and take everything after.
# If that fails, assume pure JSON.
# Actually, freqtrade 2023+ output can be noisy.
# Let's try to parse with python directly.
python3 -c "
import sys, json
content = open('$TEMP_OUTPUT').read()
try:
    # Try to find start of JSON
    start_idx = content.find('[')
    if start_idx == -1: start_idx = content.find('{')
    if start_idx != -1:
        json_str = content[start_idx:]
        # Verify it's valid JSON
        json.loads(json_str)
        print(json_str)
    else:
        sys.exit(1)
except Exception:
    sys.exit(1)
" > "$MARKETS_FILE" 2>/dev/null

if [ ! -s "$MARKETS_FILE" ]; then
    echo "Could not extract valid JSON from output. Check logs."
    cat $TEMP_OUTPUT
    rm $TEMP_OUTPUT
    exit 1
fi
rm $TEMP_OUTPUT

echo "Markets saved to $MARKETS_FILE"

# Validate Schema and Drift
echo "Validating schema..."
python3 tools/validate_markets_schema.py "$MARKETS_FILE" --prev-whitelist "$PREV_DUMP"

echo "Generating whitelist..."
WHITELIST_JSON="$PAIRLISTS_DIR/whitelist.delta.json"
WHITELIST_TXT="$PAIRLISTS_DIR/whitelist.delta.txt"

# Set FILTER_MODE env var if needed (default perps_usdt)
export FILTER_MODE="perps_usdt"
python3 tools/generate_whitelist.py "$MARKETS_FILE" > "$WHITELIST_JSON"

# Generate TXT list (symbols only)
# Extract symbols from the generated JSON
python3 -c "
import json
with open('$WHITELIST_JSON') as f:
    data = json.load(f)
for p in data['exchange']['pair_whitelist']:
    print(p)
" > "$WHITELIST_TXT"

echo "Whitelist updated at $WHITELIST_JSON"
echo "Found $(wc -l < $WHITELIST_TXT) pairs."

# Clean up old dumps (keep last 7)
ls -t $REPORTS_DIR/markets_*.json | tail -n +8 | xargs -I {} rm -- {} 2>/dev/null || true

echo "Done."
