#!/bin/bash

# Load .env file if it exists
if [ -f .env ]; then
    # Use set -a to auto-export variables
    set -a
    . .env
    set +a
else
    echo "WARNING: .env file not found. Please create one from .env.example."
fi

# Default to india_prod if not set
DELTA_ENV=${DELTA_ENV:-india_prod}

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
        echo "ERROR: Unknown DELTA_ENV: $DELTA_ENV"
        echo "Supported: india_prod, global_prod, india_testnet"
        exit 1
        ;;
esac

# Allow manual override via DELTA_BASE_URL
if [ -n "$DELTA_BASE_URL" ]; then
    BASE_URL="$DELTA_BASE_URL"
    echo "Using custom Base URL: $BASE_URL"
fi

# Export Freqtrade-compatible environment variables
# These override config.json settings

# API Key & Secret (already loaded from .env, but ensuring export)
export DELTA_API_KEY
export DELTA_API_SECRET
export FREQTRADE_API_PASSWORD

# CCXT Config for URLs
# Freqtrade maps FREQTRADE__EXCHANGE__CCXT_CONFIG__URLS__API__public -> exchange.ccxt_config.urls.api.public
export FREQTRADE__EXCHANGE__CCXT_CONFIG__URLS__API__public="$BASE_URL"
export FREQTRADE__EXCHANGE__CCXT_CONFIG__URLS__API__private="$BASE_URL"
export FREQTRADE__EXCHANGE__CCXT_CONFIG__URLS__www="$WWW_URL"

# For docker-compose.yml substitution
export DELTA_ENV
export DELTA_BASE_URL="$BASE_URL"

# Validation
if [ -z "$DELTA_API_KEY" ] || [ -z "$DELTA_API_SECRET" ]; then
    echo "WARNING: DELTA_API_KEY or DELTA_API_SECRET is missing in environment!"
fi
