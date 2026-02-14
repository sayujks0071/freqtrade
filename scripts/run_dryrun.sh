#!/bin/bash
set -e
cd "$(dirname "$0")/.."

# Source environment and helper variables
source scripts/common.sh

# Set config for dry-run
export FREQTRADE_CONFIG_FILE="config.delta.dryrun.json"

echo "Starting Freqtrade in DRY-RUN mode..."
echo "Config: $FREQTRADE_CONFIG_FILE"
echo "Whitelist: user_data/pairlists/whitelist.delta.${DELTA_ENV}.json"

docker compose up -d

echo "Freqtrade is running in background. Use 'docker compose logs -f' to view logs."
