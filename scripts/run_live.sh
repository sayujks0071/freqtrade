#!/bin/bash
set -e

# Change directory to repo root
cd "$(dirname "$0")/.."
source scripts/common.sh

echo "------------------------------------------------"
echo "Starting Freqtrade - LIVE TRADING Mode"
echo "Exchange: Delta ($DELTA_ENV)"
echo "------------------------------------------------"

# Warning
echo "WARNING: This will use REAL FUNDS."
read -p "Are you sure you want to proceed? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 1
fi

# Pre-flight checks
if [ ! -f user_data/pairlists/whitelist.delta.json ]; then
    echo "Error: Whitelist missing. Please run scripts/update_markets_and_whitelist.sh first."
    exit 1
fi

echo "Validating Exchange Connection..."
./scripts/validate_exchange.sh

# Set Config File for Docker
export FREQTRADE_CONFIG_FILE="config.delta.live.json"

echo "Launching Docker Containers..."
# Env vars from common.sh are passed to docker-compose
docker compose up -d --remove-orphans

echo "Bot is running (LIVE)!"
docker compose logs -f
