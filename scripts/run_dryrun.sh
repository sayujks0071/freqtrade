#!/bin/bash
set -e
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Source common.sh for ENV vars and URL calculation
source "$DIR/common.sh"

# Set Config File
export FREQTRADE_CONFIG_FILE="config.delta.dryrun.json"

# Validate Exchange and Whitelist
"$DIR/validate_exchange.sh"

echo "Starting Freqtrade (Dry-Run)..."
docker compose up -d

echo "Freqtrade is running in dry-run mode."
echo "Logs: user_data/logs/freqtrade.log"
echo "UI: http://localhost:8080"
