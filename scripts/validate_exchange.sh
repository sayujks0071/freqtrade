#!/bin/bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$DIR/common.sh"

echo "Checking Exchange Connection..."
if docker compose run --rm freqtrade list-exchanges --one-column | grep -q "^delta$"; then
    echo "Exchange 'delta' is available."
else
    echo "ERROR: Exchange 'delta' not found in ccxt!"
    exit 1
fi

REPORT_FILE="user_data/reports/markets_$(date +%s).json"
echo "Fetching markets from Delta ($DELTA_ENV) to $REPORT_FILE..."

docker compose run --rm freqtrade list-markets \
    --config /freqtrade/user_data/configs/${FREQTRADE_CONFIG_FILE:-config.delta.dryrun.json} \
    --exchange delta \
    --trading-mode futures \
    --print-json > "${REPORT_FILE}.tmp"

# Python script to extract JSON and validate
python3 -c "
import json
import sys
import os
import re

try:
    with open('${REPORT_FILE}.tmp', 'r') as f:
        content = f.read()

    # Try to find JSON array
    match = re.search(r'\[.*\]', content, re.DOTALL)
    if match:
        json_str = match.group(0)
    else:
        json_str = content

    try:
        markets = json.loads(json_str)
    except json.JSONDecodeError:
        print('ERROR: Could not decode JSON from markets output.')
        sys.exit(1)

    with open('$REPORT_FILE', 'w') as f:
        json.dump(markets, f, indent=2)

    if isinstance(markets, list) and len(markets) > 0 and 'symbol' in markets[0]:
        market_pairs = {m['symbol'] for m in markets}
    else:
        market_pairs = set(markets)

    config_filename = os.environ.get('FREQTRADE_CONFIG_FILE', 'config.delta.dryrun.json')
    config_filename = os.path.basename(config_filename)

    config_file = f'user_data/configs/{config_filename}'
    whitelist_file = 'user_data/pairlists/whitelist.delta.json'

    whitelist = []

    if os.path.exists(config_file):
        with open(config_file, 'r') as f:
            config = json.load(f)
            whitelist.extend(config.get('exchange', {}).get('pair_whitelist', []))

    if os.path.exists(whitelist_file):
         with open(whitelist_file, 'r') as f:
            config = json.load(f)
            whitelist.extend(config.get('exchange', {}).get('pair_whitelist', []))

    whitelist = list(set(whitelist))

    if not whitelist:
        print('WARNING: Whitelist is empty.')
        print('Attempting to auto-populate whitelist with top pairs...')

        candidates = []
        if isinstance(markets, list):
            for m in markets:
                s = m.get('symbol', '')
                # Filter for USDT futures (Delta usually format Base/Quote:Settle)
                if '/USDT:USDT' in s:
                    candidates.append(s)

        # Prioritize BTC and ETH
        top_picks = []
        for c in candidates:
            if 'BTC/USDT' in c:
                top_picks.insert(0, c)
            elif 'ETH/USDT' in c:
                top_picks.append(c)

        # Add others up to 5
        for c in candidates:
            if c not in top_picks and len(top_picks) < 5:
                top_picks.append(c)

        if top_picks:
            print(f'Populating whitelist with: {top_picks}')
            with open(whitelist_file, 'w') as f:
                json.dump({\"exchange\": {\"pair_whitelist\": top_picks}}, f, indent=4)
            whitelist = top_picks
        else:
            print('Could not find suitable pairs to populate whitelist.')
            sys.exit(0)

    missing = []
    for pair in whitelist:
        if pair not in market_pairs:
            missing.append(pair)

    if missing:
        print(f'ERROR: The following whitelist pairs are NOT active or missing on Delta ({os.environ.get(\"DELTA_ENV\")}):')
        for m in missing:
            print(f' - {m}')
        sys.exit(1)

    print(f'SUCCESS: All {len(whitelist)} whitelist pairs are valid.')

except Exception as e:
    print(f'Error validating: {e}')
    sys.exit(1)
"

rm "${REPORT_FILE}.tmp"
