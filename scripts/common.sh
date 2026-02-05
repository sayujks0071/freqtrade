#!/bin/bash

# Load .env if it exists
if [ -f .env ]; then
    set -a
    . .env
    set +a
fi

if [ -z "$DELTA_ENV" ]; then
    echo "DELTA_ENV is not set. Defaulting to global_prod."
    DELTA_ENV="global_prod"
fi

# Determine Base URL
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
        echo "Unknown DELTA_ENV: $DELTA_ENV"
        echo "Supported: india_prod, global_prod, india_testnet"
        exit 1
        ;;
esac

# Override if set
if [ -n "$DELTA_BASE_URL" ]; then
    BASE_URL="$DELTA_BASE_URL"
fi

# Export variables for Shell usage (optional, mostly for debug)
export DELTA_ENV
export DELTA_API_KEY
export DELTA_API_SECRET
export FREQTRADE__EXCHANGE__KEY="$DELTA_API_KEY"
export FREQTRADE__EXCHANGE__SECRET="$DELTA_API_SECRET"

# CCXT Config for URLs (Freqtrade specific)
export FREQTRADE__EXCHANGE__CCXT_CONFIG__URLS__API__public="$BASE_URL"
export FREQTRADE__EXCHANGE__CCXT_CONFIG__URLS__API__private="$BASE_URL"
export FREQTRADE__EXCHANGE__CCXT_CONFIG__URLS__www="$WWW_URL"

# Helper function for pre-flight checks
preflight_check() {
    echo "Running Pre-flight checks..."

    # Check 1: .env exists
    if [ ! -f .env ]; then
        echo "ERROR: .env file missing. Run bootstrap.sh first."
        exit 1
    fi

    # Check 2: Whitelist exists
    if [ ! -f user_data/pairlists/whitelist.delta.json ]; then
        echo "ERROR: whitelist.delta.json missing."
        echo "Run './scripts/validate_exchange.sh' to generate it."
        exit 1
    fi

    # Check 3: Time Sync
    echo "Checking time sync with $BASE_URL..."
    echo "System Time: $(date -u)"

    if command -v curl >/dev/null 2>&1 && command -v date >/dev/null 2>&1; then
        # Fetch Date header from Delta API
        # We use -I for HEAD request.
        SERVER_HEADER=$(curl -sI --max-time 5 "$BASE_URL")
        SERVER_DATE_STR=$(echo "$SERVER_HEADER" | grep -i "^date:" | cut -d' ' -f2- | tr -d '\r')

        if [ -n "$SERVER_DATE_STR" ]; then
            # Convert to epoch
            # Try to handle potential date parsing issues
            if SERVER_TS=$(date -d "$SERVER_DATE_STR" +%s 2>/dev/null); then
                LOCAL_TS=$(date +%s)
                DIFF=$((SERVER_TS - LOCAL_TS))
                # Absolute value
                DIFF=${DIFF#-}

                if [ "$DIFF" -gt 30 ]; then
                    echo "CRITICAL ERROR: Time drift is too high! Difference: ${DIFF}s"
                    echo "Please sync your system time using NTP."
                    exit 1
                else
                    echo "Time sync OK (Diff: ${DIFF}s)."
                fi
            else
                echo "WARNING: Could not parse server date: $SERVER_DATE_STR"
            fi
        else
             echo "WARNING: Could not retrieve Date header from exchange."
        fi
    else
        echo "WARNING: curl or date not available. Skipping strict drift check."
        echo "Ensure your system time is synced (NTP)."
    fi
}
