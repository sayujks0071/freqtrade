#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$DIR/common.sh"

echo "=== Delta Freqtrade (Dry-Run) ==="

# Preflight Check
echo "Running Preflight Checks..."
"$DIR/validate_exchange.sh"
if [ $? -ne 0 ]; then
    echo "PREFLIGHT FAILED. Aborting."
    exit 1
fi

echo "Starting Freqtrade in DRY-RUN mode..."
echo "Using config: config.delta.dryrun.json"

export FREQTRADE_CONFIG_FILE="config.delta.dryrun.json"

docker compose up -d

echo "Container started."
echo "View logs: docker compose logs -f"
