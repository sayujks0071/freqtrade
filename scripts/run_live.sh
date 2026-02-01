#!/bin/bash
set -e

# Ensure we are in the root
cd "$(dirname "$0")/.."

# Check whitelist
if [ ! -f user_data/pairlists/whitelist.delta.json ]; then
    echo "Whitelist not found. Please run update_markets_and_whitelist.sh first or bootstrap."
    exit 1
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
