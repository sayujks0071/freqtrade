#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$DIR/common.sh"

export FREQTRADE_CONFIG_FILE="config.delta.live.json"

echo "WARNING: Starting Freqtrade in LIVE TRADING mode ($DELTA_ENV)!"
echo "Press Ctrl+C to cancel in 5 seconds..."
sleep 5

# Ensure we are in the root
cd "$(dirname "$0")/.."

docker compose up -d

echo "Container started."
echo "View logs: docker compose logs -f"
