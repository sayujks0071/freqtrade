#!/bin/bash

# Load .env
if [ -f .env ]; then
    # echo "Loading .env..."
    set -a
    . .env
    set +a
else
    if [ -z "$DELTA_ENV" ]; then
        echo "No .env file found and DELTA_ENV not set."
    fi
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

echo "Configuration: ENV=$DELTA_ENV | URL=$BASE_URL"

# Export Freqtrade Variables
export FREQTRADE__EXCHANGE__KEY="$DELTA_API_KEY"
export FREQTRADE__EXCHANGE__SECRET="$DELTA_API_SECRET"

# CCXT Config for URLs
export FREQTRADE__EXCHANGE__CCXT_CONFIG__URLS__API__public="$BASE_URL"
export FREQTRADE__EXCHANGE__CCXT_CONFIG__URLS__API__private="$BASE_URL"
export FREQTRADE__EXCHANGE__CCXT_CONFIG__URLS__www="$WWW_URL"

if [ -z "$FREQTRADE__EXCHANGE__KEY" ] || [ -z "$FREQTRADE__EXCHANGE__SECRET" ]; then
    echo "WARNING: API Key or Secret is missing!"
fi
