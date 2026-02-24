#!/bin/bash
set -e
source scripts/common.sh

export FREQTRADE_CONFIG="user_data/configs/config.delta.dryrun.json"

echo "Running pre-flight checks..."
if ! bash scripts/validate_exchange.sh; then
    echo "ERROR: Validation failed. Aborting."
    exit 1
fi

echo "Starting Freqtrade in Dry-Run mode..."
echo "Config: $FREQTRADE_CONFIG"
docker compose up -d
echo "Bot started. View logs with 'docker compose logs -f'."
