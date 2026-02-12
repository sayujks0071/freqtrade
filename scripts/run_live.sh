#!/bin/bash
set -e
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
# Ensure we are in the root
cd "$(dirname "$0")/.."

source "$DIR/common.sh"

echo "Running Exchange Validation..."
"$DIR/validate_exchange.sh"

export FREQTRADE_CONFIG_FILE="config.delta.live.json"

echo "WARNING: Starting Freqtrade in LIVE TRADING mode..."
echo "Config: $FREQTRADE_CONFIG_FILE"
echo "Press Ctrl+C to abort in 5 seconds..."
sleep 5

docker compose up -d

echo "Container started."
echo "View logs: docker compose logs -f"
