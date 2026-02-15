#!/bin/bash

# Ensure we are in the root directory relative to the script location
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
ROOT_DIR="$(dirname "$DIR")"

# Load .env from root if exists
if [ -f "$ROOT_DIR/.env" ]; then
    set -a
    source "$ROOT_DIR/.env"
    set +a
fi

# Default to india_prod if not set
DELTA_ENV=${DELTA_ENV:-india_prod}
DELTA_API_KEY=${DELTA_API_KEY:-}
DELTA_API_SECRET=${DELTA_API_SECRET:-}

# Determine API URL based on Environment
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
        echo "Error: Unknown DELTA_ENV: $DELTA_ENV"
        echo "Supported values: india_prod, global_prod, india_testnet"
        exit 1
        ;;
esac

# Allow manual override via DELTA_BASE_URL
if [ -n "$DELTA_BASE_URL" ]; then
    BASE_URL="$DELTA_BASE_URL"
fi

echo "Configuration: ENV=$DELTA_ENV | API URL=$BASE_URL"

# Export Freqtrade-compatible environment variables
# These override ccxt config inside the container if mapped correctly
export FREQTRADE__EXCHANGE__KEY="$DELTA_API_KEY"
export FREQTRADE__EXCHANGE__SECRET="$DELTA_API_SECRET"

# CCXT URL Overrides
export FREQTRADE__EXCHANGE__CCXT_CONFIG__URLS__API__public="$BASE_URL"
export FREQTRADE__EXCHANGE__CCXT_CONFIG__URLS__API__private="$BASE_URL"
export FREQTRADE__EXCHANGE__CCXT_CONFIG__URLS__www="$WWW_URL"
