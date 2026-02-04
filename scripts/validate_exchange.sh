#!/bin/bash
set -e
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$DIR/common.sh"

TIMESTAMP=$(date +%s)
REPORT_FILE="user_data/reports/markets_$TIMESTAMP.json"
WHITELIST_FILE="user_data/pairlists/whitelist.delta.json"

echo "Validating Exchange Connection and Markets..."

# 1. Check Exchange
echo "Checking if 'delta' exchange is supported..."
# We suppress output but check exit code. grep -q is quiet.
if docker compose run --rm freqtrade list-exchanges --one-column | grep -q "^delta$"; then
    echo "SUCCESS: 'delta' exchange is available."
else
    echo "ERROR: 'delta' exchange not found in Freqtrade installation."
    exit 1
fi

# 2. Fetch Markets
echo "Fetching markets from Delta ($DELTA_ENV)..."
# Capture output. We expect JSON.
docker compose run --rm freqtrade list-markets \
    --exchange delta \
    --trading-mode futures \
    --print-json > "${REPORT_FILE}.tmp"

# Freqtrade logs might pollute stdout even with --print-json depending on log level.
# We attempt to find the JSON list.
# Usually it is the last block or the only block starting with [.
# We can use a python one-liner to extract the largest JSON list/object.
python3 -c "
import sys, json, re
content = open('${REPORT_FILE}.tmp').read()
# Try to find a JSON list
match = re.search(r'\[.*\]', content, re.DOTALL)
if match:
    try:
        data = json.loads(match.group(0))
        print(json.dumps(data, indent=4))
        sys.exit(0)
    except:
        pass
# If not found, exit error
sys.exit(1)
" > "$REPORT_FILE"

if [ $? -ne 0 ]; then
    echo "ERROR: Failed to parse market data from output."
    echo "Raw output (first 20 lines):"
    head -n 20 "${REPORT_FILE}.tmp"
    rm "${REPORT_FILE}.tmp"
    exit 1
fi
rm "${REPORT_FILE}.tmp"
echo "Markets saved to $REPORT_FILE"

# 3. Generate Whitelist & Validate
echo "Generating whitelist from markets..."
# Ensure tools/ exists and is usable
if [ ! -f "tools/generate_whitelist.py" ]; then
    echo "ERROR: tools/generate_whitelist.py not found."
    exit 1
fi

python3 tools/generate_whitelist.py "$REPORT_FILE" > "$WHITELIST_FILE"
if [ $? -ne 0 ]; then
    echo "ERROR: Failed to generate whitelist."
    exit 1
fi
echo "Whitelist generated at $WHITELIST_FILE"

# 4. Final Verification
# Count occurrences of 'USDT' in the whitelist file as a proxy for pair count
PAIR_COUNT=$(grep -o "/USDT:USDT" "$WHITELIST_FILE" | wc -l)

if [ "$PAIR_COUNT" -eq 0 ]; then
    echo "WARNING: No pairs found in whitelist! Check connection, filters, or market availability."
    echo "Validation FAILED."
    exit 1
else
    echo "SUCCESS: Whitelist contains $PAIR_COUNT pairs."
fi

echo "Validation Complete. System is ready."
