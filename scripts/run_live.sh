#!/bin/bash
set -e
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Source common.sh for ENV vars and URL calculation
source "$DIR/common.sh"

# Set Config File
export FREQTRADE_CONFIG_FILE="config.delta.live.json"

# Validate Exchange and Whitelist
"$DIR/validate_exchange.sh"

echo "WARNING: Starting Freqtrade in LIVE TRADING mode!"
echo "Real funds are at risk."
read -p "Are you sure? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 1
fi

docker compose up -d

echo "Freqtrade is running in LIVE mode."
echo "Logs: user_data/logs/freqtrade.log"
echo "UI: http://localhost:8080"
