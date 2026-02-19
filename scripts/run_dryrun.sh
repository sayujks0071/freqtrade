#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$DIR/common.sh"

echo "Starting Dry-Run Mode ($DELTA_ENV)..."

echo "Running Preflight Checks..."
if ! "$DIR/validate_exchange.sh"; then
    echo "ERROR: Preflight checks failed! Aborting startup."
    exit 1
fi

export FREQTRADE_CONFIG_FILE="config.delta.dryrun.json"

# Check if config exists
if [ ! -f "user_data/configs/$FREQTRADE_CONFIG_FILE" ]; then
    echo "Error: Config file user_data/configs/$FREQTRADE_CONFIG_FILE not found!"
    exit 1
fi

docker compose up -d
echo "Bot started. View logs with: docker compose logs -f"
