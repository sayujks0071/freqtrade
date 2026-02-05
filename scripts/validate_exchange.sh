#!/bin/bash
set -e

# Ensure root
cd "$(dirname "$0")/.."

echo "Testing connection and fetching markets..."
# We use dryrun config for validation usually
docker compose run --rm freqtrade list-markets \
    --config /freqtrade/user_data/configs/config.delta.dryrun.json \
    --print-json > user_data/reports/markets_validate.json

echo "Validating market schema..."
python3 tools/validate_markets_schema.py user_data/reports/markets_validate.json

# Optional: Verify existing whitelist pairs are in the dump
if [ -f user_data/pairlists/whitelist.delta.json ]; then
    echo "Verifying whitelist pairs against market dump..."
    # Simple python one-liner or script
    python3 -c "
import json, sys
with open('user_data/reports/markets_validate.json') as f:
    m = json.load(f)
    if isinstance(m, dict) and 'markets' in m: m = m['markets']
    symbols = {x['symbol'] for x in m}
with open('user_data/pairlists/whitelist.delta.json') as f:
    w = json.load(f)
    pairs = w.get('exchange', {}).get('pair_whitelist', [])
invalid = [p for p in pairs if p not in symbols]
if invalid:
    print(f'ERROR: Whitelist contains invalid pairs: {invalid}')
    sys.exit(1)
print('Whitelist verification PASS')
"
fi

echo "Exchange validation SUCCESS."
