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
