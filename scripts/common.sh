#!/bin/bash
# Common environment setup for Delta Exchange scripts

# Load .env if it exists
if [ -f .env ]; then
    # safe sourcing of env vars handling comments
    set -a
    source <(sed -e '/^#/d;/^\s*$/d' -e "s/'/'\\\\''/g" -e "s/=\(.*\)/='\1'/g" .env)
    set +a
fi

# Set default DELTA_ENV if not set
export DELTA_ENV=${DELTA_ENV:-india_testnet}

# Determine API URL based on DELTA_ENV
if [ -z "$DELTA_BASE_URL" ]; then
    case "$DELTA_ENV" in
        "india_prod")
            export DELTA_BASE_URL="https://api.india.delta.exchange"
            ;;
        "global_prod")
            export DELTA_BASE_URL="https://api.delta.exchange"
            ;;
        "india_testnet")
            export DELTA_BASE_URL="https://cdn-ind.testnet.deltaex.org"
            ;;
        *)
            echo "Unknown DELTA_ENV: $DELTA_ENV"
            exit 1
            ;;
    esac
fi

# Export for use in python scripts or other tools
export DELTA_BASE_URL
