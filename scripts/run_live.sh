#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$DIR/common.sh"

export FREQTRADE_CONFIG_FILE="config.delta.live.json"

echo "Starting Freqtrade in LIVE mode..."

# Ensure we are in the root
cd "$(dirname "$0")/.."

# Check whitelist
if [ ! -f user_data/pairlists/whitelist.delta.json ]; then
    echo "ERROR: Whitelist file user_data/pairlists/whitelist.delta.json NOT FOUND."
    echo "Please run scripts/update_markets_and_whitelist.sh first."
    exit 1
fi

echo "Validating Exchange and Markets..."
./scripts/validate_exchange.sh
if [ $? -ne 0 ]; then
    echo "Validation failed. Aborting LIVE start."
    exit 1
fi

echo "Starting Freqtrade in Docker (LIVE)..."
docker compose up -d --remove-orphans
docker compose logs -f
