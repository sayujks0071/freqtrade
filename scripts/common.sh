#!/bin/bash

# Load .env if exists
if [ -f .env ]; then
    set -a
    . .env
    set +a
fi

if [ -z "$DELTA_ENV" ]; then
    echo "DELTA_ENV is not set. Defaulting to india_testnet."
    DELTA_ENV="india_testnet"
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
        # Don't exit here to allow sourcing, but warn loudly
        echo "WARNING: Unknown environment, proceeding with defaults or manual overrides."
        ;;
esac

# Override if set
if [ -n "$DELTA_BASE_URL" ]; then
    BASE_URL="$DELTA_BASE_URL"
fi

# Export Freqtrade Variables
export FREQTRADE__EXCHANGE__KEY="${DELTA_API_KEY}"
export FREQTRADE__EXCHANGE__SECRET="${DELTA_API_SECRET}"

# CCXT Config for URLs
# These env vars are picked up by Freqtrade's configuration system
# if they match the structure FREQTRADE__<SECTION>__<KEY>.
# However, deep nested dicts in env vars can be tricky.
# Freqtrade supports flat ENV vars overriding config.
# FREQTRADE__EXCHANGE__CCXT_CONFIG__URLS__API__public
# This maps to exchange.ccxt_config.urls.api.public

if [ -n "$BASE_URL" ]; then
    export FREQTRADE__EXCHANGE__CCXT_CONFIG__URLS__API__public="$BASE_URL"
    export FREQTRADE__EXCHANGE__CCXT_CONFIG__URLS__API__private="$BASE_URL"
fi

if [ -n "$WWW_URL" ]; then
    export FREQTRADE__EXCHANGE__CCXT_CONFIG__URLS__www="$WWW_URL"
fi

# Log (to stderr to avoid breaking json pipes if sourced)
echo "Configuration: ENV=$DELTA_ENV | URL=${BASE_URL:-default}" >&2
