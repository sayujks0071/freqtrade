#!/bin/bash

# Load environment variables from .env file if it exists
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Determine API URL based on DELTA_ENV
if [ "$DELTA_ENV" == "india_prod" ]; then
    export DELTA_BASE_URL="https://api.india.delta.exchange"
elif [ "$DELTA_ENV" == "global_prod" ]; then
    export DELTA_BASE_URL="https://api.delta.exchange"
elif [ "$DELTA_ENV" == "india_testnet" ]; then
    export DELTA_BASE_URL="https://cdn-ind.testnet.deltaex.org"
else
    # Default fallback or custom URL
    export DELTA_BASE_URL=${DELTA_BASE_URL:-"https://api.delta.exchange"}
fi
