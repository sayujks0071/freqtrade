#!/bin/bash
set -e

# Ensure we are in the repo root
cd "$(dirname "$0")/.."

echo "Starting Freqtrade in DRY-RUN mode..."

# Set config file
export FREQTRADE_CONFIG_FILE="config.delta.dryrun.json"

# Run validation/preflight checks
./scripts/validate_exchange.sh

if [ $? -eq 0 ]; then
    echo "Validation passed. Starting services..."
    docker compose up -d
    echo "Freqtrade is running in DRY-RUN mode."
    echo "Logs: docker compose logs -f"
else
    echo "Validation failed. Aborting start."
    exit 1
fi
