#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$DIR/common.sh"

export FREQTRADE_CONFIG_FILE="config.delta.live.json"

echo "!!! WARNING: STARTING LIVE TRADING !!!"
echo "This involves REAL financial risk."
read -p "Are you sure? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]
then
    echo "Aborted."
    exit 1
fi

# Pre-flight
preflight_check

echo "Starting Freqtrade in LIVE mode..."
docker compose up -d

echo "Container started."
echo "View logs: docker compose logs -f"
