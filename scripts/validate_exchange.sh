#!/bin/bash
set -e

# Source common environment setup
source scripts/common.sh

CONFIG_FILE="${FREQTRADE_CONFIG:-user_data/configs/config.delta.dryrun.json}"
MARKETS_FILE="user_data/reports/markets_$(date +%s).json"

# Adjust config path for inside container
CONTAINER_CONFIG_PATH="/freqtrade/$CONFIG_FILE"

echo "Validating exchange connection and markets..."
echo "Config: $CONFIG_FILE"
echo "API URL: $FREQTRADE__EXCHANGE__CCXT_CONFIG__URLS__API__PUBLIC"

# 0. Check Time Sync
echo "Checking time synchronization..."
if command -v curl >/dev/null && command -v date >/dev/null; then
    # Use google to check time
    HTTP_DATE=$(curl -s --head http://google.com | grep ^Date: | cut -d' ' -f3-6)
    if [ -n "$HTTP_DATE" ]; then
        REMOTE_TIME=$(date -d "$HTTP_DATE" +%s)
        LOCAL_TIME=$(date +%s)
        DIFF=$((REMOTE_TIME - LOCAL_TIME))
        DIFF=${DIFF#-} # Abs

        if [ "$DIFF" -gt 30 ]; then
            echo "ERROR: System time drift is ${DIFF}s (>30s). Please sync your clock (NTP)."
            exit 1
        elif [ "$DIFF" -gt 5 ]; then
            echo "WARNING: System time drift is ${DIFF}s."
        else
            echo "Time sync OK (drift ${DIFF}s)."
        fi
    else
        echo "WARNING: Could not fetch remote time. Skipping check."
    fi
else
    echo "WARNING: curl or date not found. Skipping time check."
fi

# 1. Verify Delta exchange availability
echo "Checking if 'delta' is supported..."
if docker compose run --rm -T freqtrade list-exchanges --print-one-column | grep -q "^delta$"; then
    echo "SUCCESS: Delta exchange is supported."
else
    echo "ERROR: Delta exchange not found in freqtrade."
    exit 1
fi

# 2. Fetch markets
echo "Fetching markets from Delta..."
docker compose run --rm -T freqtrade list-markets \
    --config "$CONTAINER_CONFIG_PATH" \
    --print-json > "$MARKETS_FILE"

if [ ! -s "$MARKETS_FILE" ]; then
    echo "ERROR: Failed to fetch markets or empty response."
    rm -f "$MARKETS_FILE"
    exit 1
fi
echo "Markets saved to $MARKETS_FILE"

# 3. Verify Whitelist
echo "Verifying whitelist against fetched markets..."
python3 scripts/verify_whitelist.py "$MARKETS_FILE" "$CONFIG_FILE"

# If python script fails, set -e will exit the script.
echo "Validation successful!"
