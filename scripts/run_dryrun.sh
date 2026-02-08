#!/bin/bash
set -e
cd "$(dirname "$0")/.."

source scripts/common.sh

echo "Starting Freqtrade Delta (Dry Run)..."
echo "Env: $DELTA_ENV"

# Validate Exchange & Markets
echo "Running pre-flight checks..."
./scripts/validate_exchange.sh

# Set config file
export FREQTRADE_CONFIG_FILE=config.delta.dryrun.json

# Start
echo "Starting container..."
docker compose up -d

echo "Container started. Tailing logs (Ctrl+C to stop tailing, container runs in background)..."
docker compose logs -f freqtrade
