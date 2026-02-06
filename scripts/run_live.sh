#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$DIR/common.sh"

export FREQTRADE_CONFIG_FILE="config.delta.live.json"

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

echo "Starting Freqtrade in LIVE mode..."
echo "Using config: $FREQTRADE_CONFIG_FILE"

# Start Docker
docker compose up -d --remove-orphans

echo "Container started."
echo "View logs: docker compose logs -f"
