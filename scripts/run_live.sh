#!/bin/bash
set -e
source scripts/common.sh

export FREQTRADE_CONFIG="user_data/configs/config.delta.live.json"

echo "Running pre-flight checks..."
if ! bash scripts/validate_exchange.sh; then
    echo "ERROR: Validation failed. Aborting."
    exit 1
fi

echo "WARNING: Starting Freqtrade in LIVE TRADING mode..."
echo "Real funds will be used."
echo "Config: $FREQTRADE_CONFIG"
read -p "Are you sure? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]
then
    exit 1
fi

docker compose up -d
echo "Bot started. View logs with 'docker compose logs -f'."
