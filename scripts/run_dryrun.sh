#!/bin/bash
set -e

# Get the directory of the script
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$DIR/common.sh"

echo "=== Starting Freqtrade in DRY-RUN Mode on Delta ($DELTA_ENV) ==="

# Run Validation Steps
echo "Running pre-flight validation..."
"$DIR/validate_exchange.sh"

# Set Config File for Docker Compose
export FREQTRADE_CONFIG_FILE="config.delta.dryrun.json"

echo "Starting Container..."
docker compose up -d

echo "=== Freqtrade Dry-Run Started ==="
echo "UI: http://localhost:8080"
echo "Logs: docker compose logs -f"
