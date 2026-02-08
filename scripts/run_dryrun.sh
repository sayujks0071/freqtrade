#!/bin/bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$DIR/common.sh"

echo "---------------------------------------------------"
echo "STARTING DELTA DRY-RUN ($DELTA_ENV)"
echo "---------------------------------------------------"

export FREQTRADE_CONFIG_FILE="config.delta.dryrun.json"

echo "Running Pre-flight Checks..."
"$DIR/validate_exchange.sh"

echo "Starting Freqtrade..."
docker compose up -d

echo "---------------------------------------------------"
echo "Freqtrade started in DRY-RUN mode."
echo "Config: $FREQTRADE_CONFIG_FILE"
echo "View logs: docker compose logs -f"
echo "UI: http://localhost:8080"
echo "---------------------------------------------------"
