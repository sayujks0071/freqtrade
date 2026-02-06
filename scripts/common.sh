#!/bin/bash

# Load .env if it exists
if [ -f .env ]; then
    set -o allexport
    source .env
    set +o allexport
fi

# Default to india_prod if not set
DELTA_ENV=${DELTA_ENV:-india_prod}

echo "Detected DELTA_ENV=${DELTA_ENV}"

case "$DELTA_ENV" in
    india_prod)
        BASE_URL="https://api.india.delta.exchange"
        WWW_URL="https://india.delta.exchange"
        ;;
    global_prod)
        BASE_URL="https://api.delta.exchange"
        WWW_URL="https://www.delta.exchange"
        ;;
    india_testnet)
        BASE_URL="https://cdn-ind.testnet.deltaex.org"
        WWW_URL="https://testnet.delta.exchange"
        ;;
    *)
        echo "Error: Unknown DELTA_ENV '$DELTA_ENV'. Must be one of: india_prod, global_prod, india_testnet"
        exit 1
        ;;
esac

# Export Freqtrade overrides for CCXT URLs
export FREQTRADE__EXCHANGE__CCXT_CONFIG__URLS__API__public=$BASE_URL
export FREQTRADE__EXCHANGE__CCXT_CONFIG__URLS__API__private=$BASE_URL
export FREQTRADE__EXCHANGE__CCXT_CONFIG__URLS__www=$WWW_URL

echo "Configured for ${BASE_URL}"

check_time_drift() {
    echo "Checking time drift..."
    # Get server date header. curl -I fetches headers.
    SERVER_DATE_HEADER=$(curl -sI "$BASE_URL" | grep -i "^date:" | head -n1 | cut -d' ' -f2-)

    if [ -z "$SERVER_DATE_HEADER" ]; then
        echo "Error: Could not fetch date from $BASE_URL"
        exit 1
    fi

    # Convert to timestamp (requires GNU date or compatible)
    if date --version >/dev/null 2>&1; then
        SERVER_TS=$(date -d "$SERVER_DATE_HEADER" +%s)
        LOCAL_TS=$(date +%s)
    else
        # Mac/BSD fallback
        SERVER_TS=$(date -j -f "%a, %d %b %Y %H:%M:%S %Z" "$SERVER_DATE_HEADER" +%s)
        LOCAL_TS=$(date +%s)
    fi

    DIFF=$((SERVER_TS - LOCAL_TS))
    # Absolute value
    ABS_DIFF=${DIFF#-}

    echo "Time drift: ${ABS_DIFF}s"

    if [ "$ABS_DIFF" -gt 30 ]; then
        echo "CRITICAL: Time drift > 30s. Please sync your clock (NTP)."
        exit 1
    fi
}

preflight_check() {
    echo "Running preflight checks..."

    check_time_drift

    if [ ! -f "user_data/reports/markets_latest.json" ]; then
        echo "ERROR: Markets dump missing (user_data/reports/markets_latest.json)."
        echo "Please run ./scripts/validate_exchange.sh first."
        exit 1
    fi

    if [ ! -f "user_data/pairlists/whitelist.delta.json" ]; then
        echo "ERROR: Whitelist file missing (user_data/pairlists/whitelist.delta.json)."
        echo "Please run ./scripts/update_markets_and_whitelist.sh or create it manually."
        exit 1
    fi

    echo "Preflight checks passed."
}
