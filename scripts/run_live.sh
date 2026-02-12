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

echo "Starting Freqtrade in LIVE mode..."
docker compose up -d

echo "Container started."
echo "View logs: docker compose logs -f"
set -e

# Ensure we are in the root
cd "$(dirname "$0")/.."

# Check whitelist and config
if [ ! -f user_data/pairlists/whitelist.delta.json ] || [ ! -f user_data/configs/config.delta.live.json ]; then
    echo "Configuration or whitelist not found. Running bootstrap..."
    ./scripts/bootstrap.sh
fi

echo "WARNING: Switching to LIVE TRADING config..."
read -p "Are you sure you want to trade real money? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]
then
    exit 1
fi

cp user_data/configs/config.delta.live.json user_data/config.json

echo "Starting Freqtrade in Docker (LIVE)..."
docker compose up -d --remove-orphans
docker compose logs -f
