#!/bin/bash

# Load .env
if [ -f .env ]; then
    set -a
    . .env
    set +a
else
    echo "WARNING: No .env file found. Proceeding with environment variables..."
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
        exit 1
        ;;
esac

# Override if set
if [ -n "$DELTA_BASE_URL" ]; then
    BASE_URL="$DELTA_BASE_URL"
fi

export DELTA_ENV
export DELTA_API_KEY
export DELTA_API_SECRET
export BASE_URL

# Freqtrade overrides
export FREQTRADE__EXCHANGE__KEY="$DELTA_API_KEY"
export FREQTRADE__EXCHANGE__SECRET="$DELTA_API_SECRET"

# CCXT URL Overrides
export FREQTRADE__EXCHANGE__CCXT_CONFIG__URLS__API__PUBLIC="$BASE_URL"
export FREQTRADE__EXCHANGE__CCXT_CONFIG__URLS__API__PRIVATE="$BASE_URL"
export FREQTRADE__EXCHANGE__CCXT_CONFIG__URLS__WWW="$WWW_URL"

echo "Using Environment: $DELTA_ENV (URL: $BASE_URL)"
