#!/bin/bash

# Load .env if it exists
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Default to india_prod if not set
DELTA_ENV=${DELTA_ENV:-india_prod}

echo "Detected DELTA_ENV=${DELTA_ENV}"

case "$DELTA_ENV" in
    india_prod)
        BASE_URL="https://api.india.delta.exchange"
        ;;
    global_prod)
        BASE_URL="https://api.delta.exchange"
        ;;
    india_testnet)
        BASE_URL="https://cdn-ind.testnet.deltaex.org"
        ;;
    *)
        echo "Error: Unknown DELTA_ENV '$DELTA_ENV'. Must be one of: india_prod, global_prod, india_testnet"
        exit 1
        ;;
esac

# Export Freqtrade overrides for CCXT URLs
export FREQTRADE__EXCHANGE__CCXT_CONFIG__URLS__API__public=$BASE_URL
export FREQTRADE__EXCHANGE__CCXT_CONFIG__URLS__API__private=$BASE_URL
# Also override 'www' if needed, but API is usually enough. CCXT might use 'www' for links.
export FREQTRADE__EXCHANGE__CCXT_CONFIG__URLS__www="https://www.delta.exchange"

echo "Configured for ${BASE_URL}"
