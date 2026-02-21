#!/bin/bash

if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

DELTA_ENV=${DELTA_ENV:-india_testnet}

if [ -n "$DELTA_BASE_URL" ]; then
    API_URL="$DELTA_BASE_URL"
elif [ "$DELTA_ENV" == "india_prod" ]; then
    API_URL="https://api.india.delta.exchange"
elif [ "$DELTA_ENV" == "global_prod" ]; then
    API_URL="https://api.delta.exchange"
elif [ "$DELTA_ENV" == "india_testnet" ]; then
    API_URL="https://cdn-ind.testnet.deltaex.org"
else
    echo "Unknown DELTA_ENV: $DELTA_ENV. Defaulting to global."
    API_URL="https://api.delta.exchange"
fi

export FREQTRADE__EXCHANGE__CCXT_CONFIG__URLS__API__PUBLIC="$API_URL"
export FREQTRADE__EXCHANGE__CCXT_CONFIG__URLS__API__PRIVATE="$API_URL"

echo "DELTA_ENV: $DELTA_ENV"
echo "Using Delta API URL: $API_URL"
