#!/bin/bash

# Default to india_testnet if not set
export DELTA_ENV=${DELTA_ENV:-india_testnet}

echo "Loading environment for DELTA_ENV: $DELTA_ENV"

# Define API URLs based on environment
if [ "$DELTA_ENV" == "india_prod" ]; then
    export DELTA_API_URL="https://api.india.delta.exchange"
    export DELTA_WWW_URL="https://india.delta.exchange"
elif [ "$DELTA_ENV" == "global_prod" ]; then
    export DELTA_API_URL="https://api.delta.exchange"
    export DELTA_WWW_URL="https://www.delta.exchange"
elif [ "$DELTA_ENV" == "india_testnet" ]; then
    export DELTA_API_URL="https://cdn-ind.testnet.deltaex.org"
    export DELTA_WWW_URL="https://testnet.delta.exchange" # check if correct
else
    echo "Unknown DELTA_ENV: $DELTA_ENV. Using defaults or manual overrides."
fi

# Allow manual override
if [ -n "$DELTA_BASE_URL" ]; then
    export DELTA_API_URL="$DELTA_BASE_URL"
fi

# Export FREQTRADE__ variables for CCXT config
# Freqtrade uses double underscore as delimiter for nested config
# exchange.ccxt_config.urls.api.public
export FREQTRADE__EXCHANGE__CCXT_CONFIG__urls__api__public="$DELTA_API_URL"
export FREQTRADE__EXCHANGE__CCXT_CONFIG__urls__api__private="$DELTA_API_URL"
# exchange.ccxt_config.urls.www
export FREQTRADE__EXCHANGE__CCXT_CONFIG__urls__www="$DELTA_WWW_URL"

echo "API URL set to: $FREQTRADE__EXCHANGE__CCXT_CONFIG__urls__api__public"
