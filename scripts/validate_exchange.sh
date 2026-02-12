#!/bin/bash
set -e
cd "$(dirname "$0")/.."

echo "Validating Exchange & Markets..."

# Run the update script which handles fetching and validation
./scripts/update_markets_and_whitelist.sh

if [ -f "user_data/pairlists/whitelist.delta.json" ]; then
    COUNT=$(grep -c ":" "user_data/pairlists/whitelist.delta.txt")
    echo "SUCCESS: Whitelist generated with $COUNT pairs."
else
    echo "FAIL: Whitelist not generated."
    exit 1
fi
