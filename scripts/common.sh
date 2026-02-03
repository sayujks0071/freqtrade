#!/bin/bash
set -e

# Load .env if present
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

if [ -z "$DELTA_ENV" ]; then
    echo "DELTA_ENV not set. Defaulting to 'global_prod'."
    DELTA_ENV="global_prod"
fi

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
        echo "Error: Unknown DELTA_ENV '$DELTA_ENV'. Options: india_prod, global_prod, india_testnet."
        exit 1
        ;;
esac

# Allow manual override
if [ -n "$DELTA_BASE_URL" ]; then
    BASE_URL="$DELTA_BASE_URL"
fi

echo "Environment: $DELTA_ENV"
echo "API Base URL: $BASE_URL"

# Export variables for Freqtrade (Docker Compose inherits these)
export FREQTRADE__EXCHANGE__KEY="$DELTA_API_KEY"
export FREQTRADE__EXCHANGE__SECRET="$DELTA_API_SECRET"

# CCXT Config Overrides
# These map to exchange['ccxt_config']['urls']['api']['public'] etc.
export FREQTRADE__EXCHANGE__CCXT_CONFIG__URLS__API__public="$BASE_URL"
export FREQTRADE__EXCHANGE__CCXT_CONFIG__URLS__API__private="$BASE_URL"
export FREQTRADE__EXCHANGE__CCXT_CONFIG__URLS__www="$WWW_URL"

# Pass DELTA_ENV for logging
export DELTA_ENV

if [ -z "$DELTA_API_KEY" ] || [ -z "$DELTA_API_SECRET" ]; then
    echo "WARNING: DELTA_API_KEY or DELTA_API_SECRET is missing."
fi
