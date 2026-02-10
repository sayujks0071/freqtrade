#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Source common functions if available
if [ -f "$DIR/common.sh" ]; then
    source "$DIR/common.sh"
fi

export FREQTRADE_CONFIG_FILE="config.delta.live.json"

# Ensure we are in the root
cd "$(dirname "$0")/.."

echo "!!! WARNING: STARTING LIVE TRADING !!!"
echo "Are you sure? (y/N)"
read -r response
if [[ ! "$response" =~ ^([yY][eE][sS]|[yY])$ ]]
then
    echo "Aborted."
    exit 1
fi

# Check whitelist
if [ ! -f user_data/pairlists/whitelist.delta.json ]; then
    echo "Whitelist not found. Please run update_markets_and_whitelist.sh first or bootstrap."
    exit 1
fi

echo "Starting Freqtrade in Docker (LIVE)..."
docker compose up -d --remove-orphans
docker compose logs -f
