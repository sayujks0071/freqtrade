#!/bin/bash
set -e
cd "$(dirname "$0")/.."

# Source environment and helper variables
source scripts/common.sh

# Set config for live
export FREQTRADE_CONFIG_FILE="config.delta.live.json"

echo "!!! WARNING: Starting Freqtrade in LIVE TRADING mode !!!"
echo "Config: $FREQTRADE_CONFIG_FILE"
echo "Whitelist: user_data/pairlists/whitelist.delta.${DELTA_ENV}.json"
echo "Waiting 5 seconds before starting..."
sleep 5

docker compose up -d

echo "Freqtrade is running in background. Use 'docker compose logs -f' to view logs."
