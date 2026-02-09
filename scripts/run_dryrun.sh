#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$DIR/common.sh"

export FREQTRADE_CONFIG_FILE="config.delta.dryrun.json"

echo "Running Preflight Validation..."
"$DIR/validate_exchange.sh"

echo "Starting Freqtrade (DRY-RUN)..."
docker compose up -d

echo "Container started."
echo "Logs: docker compose logs -f"
