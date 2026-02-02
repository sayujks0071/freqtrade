#!/bin/bash
set -e
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$DIR/common.sh"

echo "--------------------------------------------------"
echo "Starting Freqtrade - DRY RUN ($DELTA_ENV)"
echo "--------------------------------------------------"

export FREQTRADE_CONFIG_FILE="config.delta.dryrun.json"

# Run Pre-flight Checks
"$DIR/validate_exchange.sh"

echo "Starting container..."
docker compose up -d

echo "Logs:"
docker compose logs -f freqtrade
