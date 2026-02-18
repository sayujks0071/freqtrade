#!/bin/bash
set -e
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$DIR/common.sh"

echo "Starting Freqtrade in DRY-RUN mode ($DELTA_ENV)..."

# Ensure user_data directories
"$DIR/bootstrap.sh"

export FREQTRADE_CONFIG_FILE="config.delta.dryrun.json"

# Validate whitelist existence
if [ ! -f user_data/pairlists/whitelist.delta.json ]; then
    echo "Whitelist not found. Attempting to fetch..."
    "$DIR/update_markets_and_whitelist.sh"
fi

echo "Starting Docker Compose..."
docker compose up -d

echo "Logs available at: docker compose logs -f"
