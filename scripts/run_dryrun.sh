#!/bin/bash
set -e

# Change directory to repo root
cd "$(dirname "$0")/.."
source scripts/common.sh

echo "------------------------------------------------"
echo "Starting Freqtrade - DRY RUN Mode"
echo "Exchange: Delta ($DELTA_ENV)"
echo "------------------------------------------------"

# Pre-flight checks
if [ ! -f user_data/pairlists/whitelist.delta.json ]; then
    echo "Whitelist missing. Running bootstrap..."
    ./scripts/bootstrap.sh
fi

echo "Validating Exchange Connection..."
./scripts/validate_exchange.sh

# Set Config File for Docker
export FREQTRADE_CONFIG_FILE="config.delta.dryrun.json"

echo "Launching Docker Containers..."
# Env vars from common.sh are passed to docker-compose
docker compose up -d --remove-orphans

echo "Bot is running!"
docker compose logs -f
