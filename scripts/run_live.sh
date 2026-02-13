#!/bin/bash
set -e
cd "$(dirname "$0")/.."

# Load .env
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

echo "WARNING: You are about to start LIVE TRADING on Delta ($DELTA_ENV)."
echo "Ensure DELTA_API_KEY and DELTA_API_SECRET are set for the correct environment."
echo "Config: config.delta.live.json"
read -p "Are you sure? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    exit 1
fi

# Ensure whitelist exists
if [ ! -f user_data/pairlists/whitelist.delta.json ]; then
    echo "ERROR: Whitelist not found. Please run scripts/update_markets_and_whitelist.sh first."
    exit 1
fi

export FREQTRADE_CONFIG_FILE="config.delta.live.json"

docker compose up -d

echo "Live trading started."
echo "View logs: docker compose logs -f"
