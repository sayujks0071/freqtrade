#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$DIR/common.sh"

set -e

echo "Starting Preflight Checks..."

# 1. Time Drift Check
echo "Checking Time Drift..."
# Fetch headers, extract date.
# Note: Delta API base URL might not return headers on root, but usually does.
SERVER_TIME=$(curl -sI "$DELTA_BASE_URL" | grep -i "^date:" | sed 's/[Dd]ate: //g' | tr -d '\r')

if [ -z "$SERVER_TIME" ]; then
    echo "WARNING: Could not fetch server time from $DELTA_BASE_URL. Skipping drift check."
else
    # date -d is GNU date specific.
    if date --version >/dev/null 2>&1 ; then
        SERVER_EPOCH=$(date -d "$SERVER_TIME" +%s)
        LOCAL_EPOCH=$(date +%s)
        DIFF=$((LOCAL_EPOCH - SERVER_EPOCH))
        # Absolute value
        DIFF=${DIFF#-}

        echo "Server Time: $SERVER_TIME ($SERVER_EPOCH)"
        echo "Local Time:  $(date) ($LOCAL_EPOCH)"
        echo "Diff: ${DIFF}s"

        if [ "$DIFF" -gt 30 ]; then
            echo "ERROR: Time drift is too high (>30s). Please sync your clock."
            exit 1
        fi
    else
        echo "WARNING: Non-GNU date detected. Skipping precise drift check."
    fi
fi

# 2. Check Exchange Availability (via Freqtrade)
echo "Verifying Delta Exchange in Freqtrade..."
# We run list-exchanges inside docker
# We verify 'delta' is in the output.
docker compose run --rm freqtrade list-exchanges --print-one-line | grep -q "delta"
if [ $? -eq 0 ]; then
    echo "OK: Delta exchange found in CCXT."
else
    echo "ERROR: Delta exchange NOT found in CCXT!"
    exit 1
fi

# 3. Update Markets & Generate Whitelist
echo "Fetching Markets and Updating Whitelist..."
"$DIR/update_markets_and_whitelist.sh"

# 4. Verify Whitelist exists and is valid
WHITELIST_FILE="user_data/pairlists/whitelist.delta.json"
if [ ! -f "$WHITELIST_FILE" ]; then
    echo "ERROR: Whitelist file $WHITELIST_FILE was not generated!"
    exit 1
fi

# Check if whitelist is empty
COUNT=$(python3 -c "import json; print(len(json.load(open('$WHITELIST_FILE'))['exchange']['pair_whitelist']))")

if [ "$COUNT" -eq 0 ]; then
    echo "ERROR: Generated whitelist is empty! Check your connection or market filters."
    exit 1
fi

echo "Preflight Checks Passed. Whitelist contains $COUNT pairs."
