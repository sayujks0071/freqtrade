#!/bin/bash
set -e

# Source common environment setup
source scripts/common.sh

# Set config file env var
export FREQTRADE_CONFIG_FILE=config.delta.live.json

echo "Running validation..."
./scripts/validate_exchange.sh || exit 1

echo "Starting Freqtrade in LIVE mode..."
docker compose up -d

echo "Freqtrade started. Check logs with 'docker compose logs -f freqtrade'"
