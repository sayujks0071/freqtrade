#!/bin/bash
set -e

# Ensure we are in project root
cd "$(dirname "$0")/.."

echo "Starting Delta Exchange Bot (DRY-RUN)..."

# Validate first
./scripts/validate_exchange.sh

# Set config file for docker (env var substitution in docker-compose)
export FREQTRADE_CONFIG_FILE=config.delta.dryrun.json

echo "Starting container..."
docker compose up -d

echo "Done. Use 'docker compose logs -f' to monitor."
