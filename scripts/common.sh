#!/bin/bash

# Load .env if exists
if [ -f .env ]; then
    set -a
    . .env
    set +a
else
    echo "WARNING: .env file not found. Relying on existing environment variables."
fi

# Default to global_prod if not set
if [ -z "$DELTA_ENV" ]; then
    echo "NOTICE: DELTA_ENV is not set. Defaulting to 'global_prod'."
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
        echo "ERROR: Unknown DELTA_ENV: '$DELTA_ENV'"
        echo "Supported options: india_prod, global_prod, india_testnet"
        exit 1
        ;;
esac

# Allow Manual Override
if [ -n "$DELTA_BASE_URL" ]; then
    echo "NOTICE: Overriding Base URL with DELTA_BASE_URL=$DELTA_BASE_URL"
    BASE_URL="$DELTA_BASE_URL"
fi

# Export for usage in scripts
export DELTA_ENV
export BASE_URL

# Export Freqtrade-Specific Variables (used by Docker Compose)
export FREQTRADE__EXCHANGE__KEY="${DELTA_API_KEY:-}"
export FREQTRADE__EXCHANGE__SECRET="${DELTA_API_SECRET:-}"

# CCXT URL Overrides
export FREQTRADE__EXCHANGE__CCXT_CONFIG__URLS__API__public="$BASE_URL"
export FREQTRADE__EXCHANGE__CCXT_CONFIG__URLS__API__private="$BASE_URL"
export FREQTRADE__EXCHANGE__CCXT_CONFIG__URLS__www="$WWW_URL"

# Validation
if [ -z "$FREQTRADE__EXCHANGE__KEY" ] || [ -z "$FREQTRADE__EXCHANGE__SECRET" ]; then
    echo "WARNING: DELTA_API_KEY or DELTA_API_SECRET is missing."
    echo "         Authentication will fail for private endpoints."
fi
