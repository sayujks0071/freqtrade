#!/bin/bash
set -e
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$DIR/common.sh"

TIMESTAMP=$(date -u +"%Y%m%d_%H%M%S")
MARKETS_FILE="user_data/reports/markets_${TIMESTAMP}.json"
WHITELIST_JSON="user_data/pairlists/whitelist.delta.json" # Symlink target or main file
WHITELIST_TXT="user_data/pairlists/whitelist.delta.txt"
PREV_MARKETS=$(ls -t user_data/reports/markets_*.json 2>/dev/null | head -n 1)

echo "Fetching markets from Delta ($DELTA_ENV)..."

# Fetch full market dump using Python/CCXT for schema validation
python3 -c "
import ccxt
import json
import os
import sys

try:
    exchange_id = 'delta'
    exchange_class = getattr(ccxt, exchange_id)
    exchange = exchange_class({
        'apiKey': os.environ.get('DELTA_API_KEY'),
        'secret': os.environ.get('DELTA_API_SECRET'),
        'enableRateLimit': True,
    })

    # Set environment based on DELTA_ENV
    env = os.environ.get('DELTA_ENV', 'india_testnet')
    if env == 'india_prod':
        exchange.urls['api'] = 'https://api.india.delta.exchange'
    elif env == 'global_prod':
        exchange.urls['api'] = 'https://api.delta.exchange'
    elif env == 'india_testnet':
        exchange.urls['api'] = 'https://cdn-ind.testnet.deltaex.org'

    # Override base URL if provided
    base_url = os.environ.get('DELTA_BASE_URL')
    if base_url:
        exchange.urls['api'] = base_url

    print(f'Fetching futures markets from {exchange.urls["api"]}...')
    markets = exchange.load_markets()

    # Filter for futures/swap only if needed, or dump all
    # The prompt says 'futures'. Delta is mostly futures.
    # We dump everything for validation.

    # Convert to list of dicts for JSON dump
    market_list = list(markets.values())

    with open('$MARKETS_FILE', 'w') as f:
        json.dump(market_list, f, indent=4)

    print(f'Saved {len(market_list)} markets to $MARKETS_FILE')

except Exception as e:
    print(f'Error fetching markets: {e}')
    sys.exit(1)
"

if [ ! -f "$MARKETS_FILE" ]; then
    echo "Failed to generate markets file."
    exit 1
fi

echo "Validating Markets Schema..."
# Run schema validator
# Pass previous markets file for drift check if exists
if [ -z "$PREV_MARKETS" ]; then
    python3 tools/validate_markets_schema.py "$MARKETS_FILE"
else
    python3 tools/validate_markets_schema.py "$MARKETS_FILE" "$PREV_MARKETS"
fi

# Check exit code
if [ $? -ne 0 ]; then
    echo "Schema Validation FAILED. Aborting whitelist update."
    # Move failed dump to reports/markets_failed_<timestamp>.json
    mv "$MARKETS_FILE" "user_data/reports/markets_failed_${TIMESTAMP}.json"
    exit 1
fi

echo "Generating Whitelist..."
# Generate whitelist based on FILTER_MODE
WHITELIST_ENV_JSON="user_data/pairlists/whitelist.delta.${DELTA_ENV}.json"
WHITELIST_ENV_TXT="user_data/pairlists/whitelist.delta.${DELTA_ENV}.txt"

python3 tools/generate_whitelist.py "$MARKETS_FILE" > "$WHITELIST_ENV_JSON"

# Extract just the list for txt file
python3 -c "
import json
with open('$WHITELIST_ENV_JSON', 'r') as f:
    data = json.load(f)
    print('\n'.join(data['exchange']['pair_whitelist']))
" > "$WHITELIST_ENV_TXT"

echo "Generated whitelist at $WHITELIST_ENV_JSON"
echo "Generated whitelist txt at $WHITELIST_ENV_TXT"

# Update the main whitelist symlink/copy for bot usage
cp "$WHITELIST_ENV_JSON" "$WHITELIST_JSON"
echo "Updated $WHITELIST_JSON"

# Generate Diff Report
DIFF_REPORT="user_data/reports/whitelist_diff_${TIMESTAMP}.md"
echo "# Whitelist Diff Report ($TIMESTAMP)" > "$DIFF_REPORT"
if [ -n "$PREV_MARKETS" ]; then
    # Simple diff of whitelist txt (if previous txt exists)
    PREV_TXT=$(ls -t user_data/pairlists/whitelist.delta.*.txt 2>/dev/null | grep -v "$WHITELIST_ENV_TXT" | head -n 1)
    if [ -n "$PREV_TXT" ]; then
        echo "## Changes vs $PREV_TXT" >> "$DIFF_REPORT"
        diff -u "$PREV_TXT" "$WHITELIST_ENV_TXT" >> "$DIFF_REPORT" || true
    else
        echo "No previous whitelist txt found to compare." >> "$DIFF_REPORT"
    fi
else
    echo "No previous markets found to compare." >> "$DIFF_REPORT"
fi

# Cleanup old dumps (keep last 7)
echo "Cleaning up old dumps..."
ls -t user_data/reports/markets_*.json | tail -n +8 | xargs -r rm --

echo "Update Complete."
