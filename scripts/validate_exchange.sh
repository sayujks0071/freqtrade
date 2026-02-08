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
RAW_OUTPUT="user_data/reports/markets_raw_${TIMESTAMP}.txt"
REPORT_FILE="user_data/reports/markets_${TIMESTAMP}.json"
CONFIG_FILE="/freqtrade/user_data/configs/${FREQTRADE_CONFIG_FILE:-config.delta.dryrun.json}"
LOCAL_CONFIG_FILE="user_data/configs/${FREQTRADE_CONFIG_FILE:-config.delta.dryrun.json}"

echo "Saving markets to $REPORT_FILE using config $CONFIG_FILE"

# Run list-markets
docker compose run --rm freqtrade list-markets \
    --config "$CONFIG_FILE" \
    --exchange delta \
    --trading-mode futures \
    --print-json > "$RAW_OUTPUT"

# Extract JSON
python3 scripts/extract_json.py < "$RAW_OUTPUT" > "$REPORT_FILE"

if [ ! -s "$REPORT_FILE" ] || [ "$(cat $REPORT_FILE)" == "[]" ]; then
    echo "ERROR: Failed to fetch markets or parse output."
    echo "Raw Output:"
    cat "$RAW_OUTPUT"
    rm -f "$RAW_OUTPUT" "$REPORT_FILE"
    exit 1
fi
rm "$RAW_OUTPUT"
echo "Markets saved to $REPORT_FILE"

# 4. UPDATE/VALIDATE WHITELIST
echo "[4/4] Updating Whitelist in $LOCAL_CONFIG_FILE..."

# Update whitelist in config using our new script
python3 scripts/update_config_whitelist.py \
    --markets "$REPORT_FILE" \
    --config "$LOCAL_CONFIG_FILE"

if [ $? -ne 0 ]; then
    echo "ERROR: Failed to update whitelist."
    exit 1
fi

echo "---------------------------------------------------"
echo "VALIDATION SUCCESSFUL & CONFIG UPDATED"
echo "---------------------------------------------------"
