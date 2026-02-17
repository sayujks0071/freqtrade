#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$SCRIPT_DIR/.."
source "$SCRIPT_DIR/common.sh"

echo "Validating Delta Exchange Connection ($DELTA_ENV)..."

MARKETS_DUMP="$BASE_DIR/user_data/reports/markets_dump_validation.json"
WHITELIST_FILE="$BASE_DIR/user_data/pairlists/whitelist.delta.json"

# 1. Check Connection & Markets
echo "Fetching markets to $MARKETS_DUMP..."

if ! command -v freqtrade &> /dev/null; then
    # If freqtrade is not in PATH, try to use docker run
    echo "freqtrade command not found. Using docker..."
    # We need to pass env vars to docker
    docker compose run --rm \
        -e DELTA_ENV="$DELTA_ENV" \
        -e DELTA_API_KEY="$DELTA_API_KEY" \
        -e DELTA_API_SECRET="$DELTA_API_SECRET" \
        freqtrade list-markets --exchange delta --print-json > "$MARKETS_DUMP"
else
    # Assuming freqtrade is installed and env vars are set
    freqtrade list-markets --exchange delta --print-json > "$MARKETS_DUMP"
fi

if [ ! -s "$MARKETS_DUMP" ]; then
    echo "Error: Failed to fetch markets from Delta Exchange!"
    exit 1
fi

echo "Markets fetched successfully."

# 2. Validate Schema
echo "Validating market schema..."
python3 "$BASE_DIR/tools/validate_markets_schema.py" \
    --markets "$MARKETS_DUMP" \
    --env "$DELTA_ENV" \
    --out-report "$BASE_DIR/user_data/reports/validation_report.md"

if [ $? -ne 0 ]; then
    echo "Schema validation FAILED!"
    exit 1
fi
echo "Schema validation PASSED."

# 3. Validate Whitelist (if exists)
if [ -f "$WHITELIST_FILE" ]; then
    echo "Validating current whitelist against fetched markets..."

    cat <<'EOF' > "$BASE_DIR/tools/temp_verify_whitelist.py"
import json
import sys
import os

whitelist_path = sys.argv[1]
markets_path = sys.argv[2]

try:
    with open(whitelist_path, 'r') as f:
        whitelist = json.load(f)

    with open(markets_path, 'r') as f:
        markets_data = json.load(f)

    # Handle dict or list format
    if isinstance(markets_data, dict):
        markets = list(markets_data.values())
    else:
        markets = markets_data

    market_symbols = set(m.get('symbol') for m in markets if m.get('symbol'))

    missing = [p for p in whitelist if p not in market_symbols]

    if missing:
        print(f"Error: Whitelist contains {len(missing)} pairs not found in exchange: {missing[:5]}...")
        sys.exit(1)

    print(f"All {len(whitelist)} whitelist pairs exist on exchange.")

except Exception as e:
    print(f"Error validating whitelist: {e}")
    sys.exit(1)
EOF

    python3 "$BASE_DIR/tools/temp_verify_whitelist.py" "$WHITELIST_FILE" "$MARKETS_DUMP"
    RESULT=$?
    rm "$BASE_DIR/tools/temp_verify_whitelist.py"

    if [ $RESULT -ne 0 ]; then
        echo "Whitelist validation FAILED!"
        exit 1
    fi
else
    echo "No whitelist found at $WHITELIST_FILE. Skipping check."
fi

echo "Exchange validation COMPLETE."
