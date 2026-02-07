#!/bin/bash
set -e

# Source common environment setup
source scripts/common.sh

# Set config file env var
export FREQTRADE_CONFIG_FILE=config.delta.dryrun.json

echo "Running validation..."
./scripts/validate_exchange.sh || exit 1

echo "Starting Freqtrade in Dry Run mode..."
docker compose up -d

echo "Freqtrade started. Check logs with 'docker compose logs -f freqtrade'"
