#!/bin/bash
set -e
cd "$(dirname "$0")/.."

source scripts/common.sh

echo "Validating Delta Exchange Connection ($DELTA_ENV)..."
echo "Base URL: $DELTA_BASE_URL"

# 1. Connection Check
# Simple ping to the base URL or a health endpoint if known.
# Delta often has /v2/products (public). Let's try root or a known endpoint.
# Using /v2/products (tickers) as a lightweight check.
if ! curl -s -f -o /dev/null "$DELTA_BASE_URL/v2/products" && ! curl -s -f -o /dev/null "$DELTA_BASE_URL"; then
    echo "ERROR: Cannot reach Delta Exchange API at $DELTA_BASE_URL"
    exit 1
fi
echo "Connection OK."

# 2. Fetch Markets
echo "Fetching markets (futures)..."
TIMESTAMP=$(date -u +"%Y%m%d_%H%M%S")
REPORT_DIR="user_data/reports"
mkdir -p "$REPORT_DIR"
MARKETS_FILE="$REPORT_DIR/markets_${TIMESTAMP}.json"

# We use a temp file because docker output might contain logs
TEMP_OUTPUT=$(mktemp)

# Run list-markets
# We need to make sure we pass the right config/args.
# We use dryrun config.
docker compose run --rm freqtrade list-markets \
    --config /freqtrade/user_data/configs/config.delta.dryrun.json \
    --exchange delta \
    --trading-mode futures \
    --print-json > "$TEMP_OUTPUT" 2>/dev/null || true

# Check if file is empty
if [ ! -s "$TEMP_OUTPUT" ]; then
    echo "ERROR: Failed to fetch markets (empty output)."
    rm "$TEMP_OUTPUT"
    exit 1
fi

# Extract JSON list (sometimes freqtrade logs to stdout even with print-json?)
# Usually --print-json output is pure JSON if no errors.
# But we can try to filter just in case.
# If it starts with [, it's good.
mv "$TEMP_OUTPUT" "$MARKETS_FILE"
echo "Markets saved to $MARKETS_FILE"

# 3. Validate Schema
echo "Validating Schema..."
# Find previous dump for drift check (optional)
PREV_DUMP=$(ls -t "$REPORT_DIR"/markets_*.json 2>/dev/null | grep -v "$TIMESTAMP" | head -n 1 || echo "")

python3 tools/validate_markets_schema.py "$MARKETS_FILE" $PREV_DUMP

# 4. Validate Current Whitelist (if exists)
WHITELIST_FILE="user_data/pairlists/whitelist.delta.json"
if [ -f "$WHITELIST_FILE" ]; then
    echo "Validating existing whitelist against new dump..."
    python3 -c "
import json
import sys

try:
    with open('$MARKETS_FILE') as f:
        data = json.load(f)
        if isinstance(data, dict) and 'markets' in data:
            data = data['markets']
        markets = {m['symbol'] for m in data}

    with open('$WHITELIST_FILE') as f:
        wl_data = json.load(f)
        whitelist = wl_data.get('exchange', {}).get('pair_whitelist', [])

    missing = [p for p in whitelist if p not in markets]

    if missing:
        print(f'ERROR: The following pairs in whitelist are NOT active/missing:')
        for p in missing:
            print(f' - {p}')
        sys.exit(1)

    print(f'Whitelist ({len(whitelist)} pairs) is valid.')

except Exception as e:
    print(f'Error validating whitelist: {e}')
    sys.exit(1)
"
fi

echo "Exchange Validation Complete."
