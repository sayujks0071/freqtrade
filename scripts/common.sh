#!/bin/bash

# Load .env
# We check if .env exists in the current directory or the parent directory (if run from scripts/)
if [ -f .env ]; then
    set -a
    . .env
    set +a
elif [ -f ../.env ]; then
    set -a
    . ../.env
    set +a
else
    # Only echo warning if not running in CI or non-interactive
    if [ -t 1 ]; then
        echo "No .env file found. Using environment variables."
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

# Export Freqtrade Variables for Docker Compose
export FREQTRADE__EXCHANGE__KEY="$DELTA_API_KEY"
export FREQTRADE__EXCHANGE__SECRET="$DELTA_API_SECRET"

# CCXT Config for URLs
export FREQTRADE__EXCHANGE__CCXT_CONFIG__URLS__API__public="$BASE_URL"
export FREQTRADE__EXCHANGE__CCXT_CONFIG__URLS__API__private="$BASE_URL"
export FREQTRADE__EXCHANGE__CCXT_CONFIG__URLS__www="$WWW_URL"

if [ -z "$FREQTRADE__EXCHANGE__KEY" ] || [ -z "$FREQTRADE__EXCHANGE__SECRET" ]; then
    # Warn but don't exit, as some commands (like list-exchanges) might work without keys
    echo "WARNING: API Key or Secret is missing! Trading will fail."
fi
