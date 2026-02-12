#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$DIR/common.sh"

export FREQTRADE_CONFIG_FILE="config.delta.dryrun.json"
export FREQTRADE_STRATEGY="DeltaSafeStrategy"

echo "Starting Freqtrade in DRY-RUN mode..."
echo "Strategy: $FREQTRADE_STRATEGY"
echo "Config: $FREQTRADE_CONFIG_FILE"

# Ensure we are in root
cd "$(dirname "$0")/.."

# Check whitelist
if [ ! -f "user_data/pairlists/whitelist.delta.json" ]; then
    echo "Whitelist not found. Running validation/refresh..."
    bash "scripts/validate_exchange.sh"
fi

echo "Starting container..."
docker compose up -d

echo "Container started."
echo "View logs: docker compose logs -f"
