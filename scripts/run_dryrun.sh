#!/bin/bash
source "$(dirname "$0")/common.sh"

echo "Starting Freqtrade in DRY-RUN mode on $DELTA_ENV..."
echo "Using config: config.delta.dryrun.json"

export FREQTRADE_CONFIG_FILE=config.delta.dryrun.json

docker compose up -d

echo "Container started."
echo "View logs with: docker compose logs -f freqtrade"
echo "Access UI at: http://localhost:8080"
