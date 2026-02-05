#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$DIR/common.sh"

export FREQTRADE_CONFIG_FILE="config.delta.dryrun.json"

# Pre-flight
preflight_check

echo "Starting Freqtrade in DRY-RUN mode..."
docker compose up -d

echo "Container started."
echo "View logs: docker compose logs -f"
