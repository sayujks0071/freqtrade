#!/bin/bash

# Load .env
if [ -f .env ]; then
    source .env
fi

# Determine DELTA_BASE_URL based on DELTA_ENV if not set
if [ -z "$DELTA_BASE_URL" ]; then
    if [ "$DELTA_ENV" = "india_prod" ]; then
        export DELTA_BASE_URL="https://api.india.delta.exchange"
    elif [ "$DELTA_ENV" = "global_prod" ]; then
        export DELTA_BASE_URL="https://api.delta.exchange"
    elif [ "$DELTA_ENV" = "india_testnet" ]; then
        export DELTA_BASE_URL="https://cdn-ind.testnet.deltaex.org"
    else
        # Default to india_prod if not specified or unknown (safe default for Delta India users)
        # But maybe safer to fail if unknown? Let's default to global if nothing set, or fail.
        # The prompt says "autodetect/validate the API base URLs".
        # Let's assume global prod if nothing set, but warn.
        if [ -z "$DELTA_ENV" ]; then
            echo "WARNING: DELTA_ENV not set. Defaulting to global_prod."
            export DELTA_BASE_URL="https://api.delta.exchange"
        else
            echo "WARNING: Unknown DELTA_ENV='$DELTA_ENV'. Please set DELTA_BASE_URL manually."
        fi
    fi
fi

# Export for sub-shells
export DELTA_BASE_URL
export DELTA_ENV
