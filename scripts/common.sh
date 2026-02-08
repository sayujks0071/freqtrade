#!/bin/bash
# scripts/common.sh
# Common environment variables and helper functions

# Load .env if it exists
if [ -f .env ]; then
    # Filter comments and empty lines
    export $(grep -v '^#' .env | xargs)
fi

# Defaults
export DELTA_ENV=${DELTA_ENV:-india_testnet}
export FREQTRADE_IMAGE=${FREQTRADE_IMAGE:-freqtradeorg/freqtrade:stable}
export FREQTRADE_CONFIG_FILE=${FREQTRADE_CONFIG_FILE:-config.delta.dryrun.json}

# Delta Exchange Base URLs
case "$DELTA_ENV" in
    india_prod)
        DEFAULT_BASE_URL="https://api.india.delta.exchange"
        ;;
    global_prod)
        DEFAULT_BASE_URL="https://api.delta.exchange"
        ;;
    india_testnet)
        DEFAULT_BASE_URL="https://cdn-ind.testnet.deltaex.org"
        ;;
    *)
        echo "Unknown DELTA_ENV: $DELTA_ENV. Defaulting to india_testnet."
        DEFAULT_BASE_URL="https://cdn-ind.testnet.deltaex.org"
        ;;
esac

# Allow override
export DELTA_BASE_URL=${DELTA_BASE_URL:-$DEFAULT_BASE_URL}

echo "Environment: $DELTA_ENV"
echo "Base URL: $DELTA_BASE_URL"

# Helper to check docker
check_docker() {
    if ! command -v docker &> /dev/null; then
        echo "Error: Docker is not installed or not in PATH."
        exit 1
    fi
}
