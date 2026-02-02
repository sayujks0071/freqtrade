#!/bin/bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$DIR/common.sh"

echo "--------------------------------------------------"
echo "Running Pre-flight Validation for Delta ($DELTA_ENV)"
echo "--------------------------------------------------"

# 0. Check System Time
SYSTEM_TIME=$(date)
echo "System Time: $SYSTEM_TIME"
echo "Ensure your system clock is synchronized (NTP). Excessive drift will cause API errors."

# 1. Validate Exchange availability (and Docker image)
echo "Checking Exchange: Delta..."
if ! docker compose run --rm freqtrade list-exchanges --print-json | grep -q "delta"; then
    echo "ERROR: 'delta' exchange not found in Freqtrade or failed to run."
    exit 1
fi
echo "Exchange 'delta' is supported."

# 2. Fetch Markets
TIMESTAMP=$(date -u +"%Y%m%d_%H%M%S")
REPORT_DIR="user_data/reports"
mkdir -p "$REPORT_DIR"
MARKETS_FILE="$REPORT_DIR/markets_${TIMESTAMP}.json"

echo "Fetching markets..."
# We use a config to ensure we get futures if specified, though list-markets with --exchange delta works too.
# We pass --trading-mode futures explicitly.
docker compose run --rm freqtrade list-markets \
    --exchange delta \
    --trading-mode futures \
    --print-json > "${MARKETS_FILE}.tmp"

# Extract JSON (from first [ to last ])
# This handles pretty-printed JSON or mixed output
sed -n '/\[/,/\]/p' "${MARKETS_FILE}.tmp" > "$MARKETS_FILE"

# Check if valid
if [ ! -s "$MARKETS_FILE" ]; then
    echo "Error: Failed to fetch markets or parse output."
    echo "Raw Output:"
    cat "${MARKETS_FILE}.tmp"
    rm -f "$MARKETS_FILE" "${MARKETS_FILE}.tmp"
    exit 1
fi
rm "${MARKETS_FILE}.tmp"
echo "Markets saved to $MARKETS_FILE"

# 3. Validate & Auto-Populate Whitelist
echo "Validating Whitelist..."
# We check the whitelist file referenced in docker-compose: user_data/pairlists/whitelist.delta.json
WHITELIST_FILE="user_data/pairlists/whitelist.delta.json"

if [ ! -f "$WHITELIST_FILE" ]; then
    echo "WARNING: Whitelist file $WHITELIST_FILE not found. Creating empty container."
    echo '{"exchange": {"pair_whitelist": []}}' > "$WHITELIST_FILE"
fi

python3 -c "
import json
import sys

try:
    with open('$MARKETS_FILE', 'r') as f:
        markets = json.load(f) # List of dicts or strings. Freqtrade list-markets --print-json returns list of dicts usually.
        # Wait, freqtrade list-markets --print-json returns a list of dictionaries with 'symbol', 'spot', 'future' etc details?
        # OR just a list of pair strings if --print-one-column is not used?
        # Actually list-markets --print-json output is a list of dictionaries representing markets.
        # But wait, earlier I used grep for [...].
        # Let's verify what list-markets returns. usually it is detailed.

    # Extract symbols from markets
    market_symbols = set()
    if isinstance(markets, list) and len(markets) > 0:
        if isinstance(markets[0], dict):
             market_symbols = {m['symbol'] for m in markets}
        elif isinstance(markets[0], str):
             market_symbols = set(markets)

    with open('$WHITELIST_FILE', 'r') as f:
        wl_data = json.load(f)

    whitelist = wl_data.get('exchange', {}).get('pair_whitelist', [])

    # Auto-populate if empty or dummy (<= 2 pairs)
    if len(whitelist) <= 2:
        print('Whitelist is empty or minimal. Auto-populating from market dump...')
        # Filter for USDT futures if possible, or just take all
        # Assuming markets is list of dicts with 'symbol'
        new_whitelist = sorted(list(market_symbols))
        # Limit to 20 for safety if too many
        if len(new_whitelist) > 20:
            print(f'Limiting to top 20 of {len(new_whitelist)} pairs.')
            new_whitelist = new_whitelist[:20]

        wl_data['exchange'] = wl_data.get('exchange', {})
        wl_data['exchange']['pair_whitelist'] = new_whitelist

        with open('$WHITELIST_FILE', 'w') as f:
            json.dump(wl_data, f, indent=4)

        print(f'Populated whitelist with {len(new_whitelist)} pairs.')
        whitelist = new_whitelist

    missing = []
    for pair in whitelist:
        if pair not in market_symbols:
            missing.append(pair)

    if missing:
        print(f'ERROR: The following pairs in whitelist are NOT found in fetched markets:')
        for m in missing:
            print(f' - {m}')
        sys.exit(1)

    print(f'SUCCESS: All {len(whitelist)} whitelist pairs are present in market data.')

except Exception as e:
    print(f'Error validating whitelist: {e}')
    sys.exit(1)
"

if [ $? -eq 0 ]; then
    echo "Pre-flight checks PASSED."
else
    echo "Pre-flight checks FAILED."
    exit 1
fi
