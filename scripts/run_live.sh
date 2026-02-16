#!/bin/bash
set -e

# Ensure we are in project root
cd "$(dirname "$0")/.."

echo "Starting Delta Exchange Bot (LIVE TRADING)..."
echo "WARNING: REAL MONEY INVOLVED."
read -p "Are you sure? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    exit 1
fi

# Validate first
./scripts/validate_exchange.sh

# Set config file
export FREQTRADE_CONFIG_FILE=config.delta.live.json

echo "Starting container..."
docker compose up -d

echo "Done. Use 'docker compose logs -f' to monitor."
