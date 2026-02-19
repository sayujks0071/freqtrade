#!/bin/bash

# Load .env file
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Delta Exchange Environment URL Logic
DELTA_ENV=${DELTA_ENV:-india_testnet}

if [ -n "$DELTA_BASE_URL" ]; then
    BASE_URL="$DELTA_BASE_URL"
else
    case "$DELTA_ENV" in
        "india_prod")
            BASE_URL="https://api.india.delta.exchange"
            ;;
        "global_prod")
            BASE_URL="https://api.delta.exchange"
            ;;
        "india_testnet")
            BASE_URL="https://cdn-ind.testnet.deltaex.org"
            ;;
        *)
            echo "Unknown DELTA_ENV: $DELTA_ENV. Using default global."
            BASE_URL="https://api.delta.exchange"
            ;;
    esac
fi

# Export CCXT URL overrides for Freqtrade (Docker)
# CCXT structure for Delta might differ, but generally:
# 'api': {'public': '...', 'private': '...'}
export FREQTRADE__EXCHANGE__CCXT_CONFIG__URLS__API__public="$BASE_URL"
export FREQTRADE__EXCHANGE__CCXT_CONFIG__URLS__API__private="$BASE_URL"
export FREQTRADE__EXCHANGE__CCXT_CONFIG__URLS__www="https://www.delta.exchange"

echo "Using Delta Environment: $DELTA_ENV ($BASE_URL)"
