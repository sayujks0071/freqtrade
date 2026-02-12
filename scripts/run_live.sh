#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$DIR/common.sh"

export FREQTRADE_CONFIG_FILE="config.delta.live.json"
export FREQTRADE_STRATEGY="DeltaSafeStrategy"

echo "!!! WARNING: STARTING LIVE TRADING ON $DELTA_ENV !!!"
echo "REAL MONEY IS AT RISK."
echo "Strategy: $FREQTRADE_STRATEGY"
echo "Daily Loss Limit: ${DAILY_LOSS_LIMIT:-"Default (-5%)"}"

# Verification
if [ -z "$DELTA_API_KEY" ] || [ -z "$DELTA_API_SECRET" ]; then
    echo "ERROR: API Credentials missing!"
    exit 1
fi

if [[ "$DELTA_API_KEY" == *"your_api_key"* ]]; then
     echo "ERROR: Default API Key detected. Edit .env!"
     exit 1
fi

echo "Are you sure? (Type 'YES' to confirm)"
read -r response
if [ "$response" != "YES" ]; then
    echo "Aborted."
    exit 1
fi

# Ensure we are in root
cd "$(dirname "$0")/.."

# Check whitelist
if [ ! -f "user_data/pairlists/whitelist.delta.json" ]; then
    echo "Whitelist not found. Running validation/refresh..."
    bash "scripts/validate_exchange.sh"
fi

echo "Starting container in LIVE mode..."
docker compose up -d

echo "Container started (LIVE)."
echo "Monitor logs closely: docker compose logs -f"
