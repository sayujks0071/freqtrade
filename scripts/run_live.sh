#!/bin/bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$DIR/common.sh"

echo "---------------------------------------------------"
echo "!!! STARTING DELTA LIVE TRADING ($DELTA_ENV) !!!"
echo "---------------------------------------------------"
echo "WARNING: REAL FUNDS AT RISK."
echo "Press Ctrl+C to abort in 5 seconds..."
sleep 5

export FREQTRADE_CONFIG_FILE="config.delta.live.json"

echo "Running Pre-flight Checks..."
"$DIR/validate_exchange.sh"

echo "Starting Freqtrade..."
docker compose up -d

echo "---------------------------------------------------"
echo "Freqtrade started in LIVE TRADING mode."
echo "Config: $FREQTRADE_CONFIG_FILE"
echo "View logs: docker compose logs -f"
echo "UI: http://localhost:8080"
echo "---------------------------------------------------"
