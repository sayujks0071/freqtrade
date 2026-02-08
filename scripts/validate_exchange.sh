#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$DIR/common.sh"

echo "---------------------------------------------------"
echo "VALIDATING DELTA EXCHANGE ENVIRONMENT ($DELTA_ENV)"
echo "---------------------------------------------------"

# 1. TIME DRIFT CHECK
echo "[1/4] Checking Time Drift..."
SERVER_DATE=$(curl -sI "$BASE_URL/v2/products" | grep -i "^date:" | cut -d' ' -f2- | tr -d '\r')

if [ -z "$SERVER_DATE" ]; then
    echo "ERROR: Could not fetch server time from $BASE_URL"
    exit 1
fi

SERVER_EPOCH=$(date -d "$SERVER_DATE" +%s)
LOCAL_EPOCH=$(date +%s)
DIFF=$((SERVER_EPOCH - LOCAL_EPOCH))
ABS_DIFF=${DIFF#-}

echo "Server Time: $SERVER_DATE ($SERVER_EPOCH)"
echo "Local Time:  $(date) ($LOCAL_EPOCH)"
echo "Drift:       ${ABS_DIFF}s"

if [ "$ABS_DIFF" -gt 30 ]; then
    echo "CRITICAL: Time drift is too high (>30s). Please sync your clock (NTP)."
    exit 1
fi
echo "Time Check: PASS"

# 2. CHECK EXCHANGE AVAILABILITY
echo "[2/4] Checking 'delta' exchange availability..."
echo "Skipping explicit 'list-exchanges' (assumed valid in image)."

# 3. FETCH MARKETS
echo "[3/4] Fetching Markets..."
TIMESTAMP=$(date +%s)
REPORT_FILE="user_data/reports/markets_${TIMESTAMP}.json"
CONFIG_FILE="/freqtrade/user_data/configs/${FREQTRADE_CONFIG_FILE:-config.delta.dryrun.json}"

echo "Saving markets to $REPORT_FILE using config $CONFIG_FILE"

# Run list-markets
docker compose run --rm freqtrade list-markets \
    --config "$CONFIG_FILE" \
    --exchange delta \
    --trading-mode futures \
    --print-json > "${REPORT_FILE}.tmp"

# Extract JSON array (lines starting with [)
grep -o '\[.*\]' "${REPORT_FILE}.tmp" > "$REPORT_FILE" || true

if [ ! -s "$REPORT_FILE" ]; then
    echo "ERROR: Failed to fetch markets or parse output."
    echo "Raw Output (tail):"
    tail -n 20 "${REPORT_FILE}.tmp"
    rm -f "${REPORT_FILE}.tmp"
    exit 1
fi
rm "${REPORT_FILE}.tmp"
echo "Markets saved to $REPORT_FILE"

# 4. VALIDATE WHITELIST
echo "[4/4] Validating Whitelist..."

LOCAL_CONFIG_FILE="user_data/configs/${FREQTRADE_CONFIG_FILE:-config.delta.dryrun.json}"

if [ ! -f "$LOCAL_CONFIG_FILE" ]; then
    echo "ERROR: Config file $LOCAL_CONFIG_FILE not found!"
    exit 1
fi

python3 -c "
import json
import sys

try:
    report_file = sys.argv[1]
    config_file = sys.argv[2]

    # Load Markets
    with open(report_file, 'r') as f:
        markets = json.load(f) # List of strings ['BTC/USDT:USDT', ...]

    # Load Config
    with open(config_file, 'r') as f:
        config = json.load(f)

    whitelist = config.get('exchange', {}).get('pair_whitelist', [])

    print(f'Checking {len(whitelist)} pairs against {len(markets)} active markets...')

    missing = []
    for pair in whitelist:
        if pair not in markets:
            missing.append(pair)

    if missing:
        print('ERROR: The following pairs are in whitelist but NOT active on Delta:')
        for m in missing:
            print(f' - {m}')
        sys.exit(1)

    print('SUCCESS: All whitelist pairs are valid.')

except Exception as e:
    print(f'Error during validation: {e}')
    sys.exit(1)
" "$REPORT_FILE" "$LOCAL_CONFIG_FILE"

if [ $? -eq 0 ]; then
    echo "---------------------------------------------------"
    echo "VALIDATION SUCCESSFUL"
    echo "---------------------------------------------------"
else
    echo "---------------------------------------------------"
    echo "VALIDATION FAILED"
    echo "---------------------------------------------------"
    exit 1
fi
