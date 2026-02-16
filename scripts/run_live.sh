#!/bin/bash
set -e

# Ensure we are in the repo root
cd "$(dirname "$0")/.."

echo "WARNING: YOU ARE ABOUT TO START LIVE TRADING WITH REAL MONEY."
echo "Ensure your strategy is profitable and risk management is set."
read -p "Are you sure? (type 'YES' to confirm): " CONFIRM

if [ "$CONFIRM" != "YES" ]; then
    echo "Aborted."
    exit 1
fi

echo "Starting Freqtrade in LIVE mode..."

# Set config file
export FREQTRADE_CONFIG_FILE="config.delta.live.json"

# Run validation/preflight checks
./scripts/validate_exchange.sh

if [ $? -eq 0 ]; then
    echo "Validation passed. Starting services..."
    docker compose up -d
    echo "Freqtrade is running in LIVE mode."
    echo "Logs: docker compose logs -f"
else
    echo "Validation failed. Aborting start."
    exit 1
fi
