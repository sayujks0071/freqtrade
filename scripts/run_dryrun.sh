#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Source common functions if available
if [ -f "$DIR/common.sh" ]; then
    source "$DIR/common.sh"
fi

export FREQTRADE_CONFIG_FILE="config.delta.dryrun.json"

# Ensure we are in the root
cd "$(dirname "$0")/.."

echo "Starting Freqtrade in DRY-RUN mode..."

# Check whitelist
if [ ! -f user_data/pairlists/whitelist.delta.json ]; then
    echo "Whitelist not found. Running bootstrap..."
    ./scripts/bootstrap.sh
fi

echo "Starting Freqtrade in Docker..."
docker compose up -d --remove-orphans
docker compose logs -f
