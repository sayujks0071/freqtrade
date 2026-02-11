#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$DIR/common.sh"

export FREQTRADE_CONFIG_FILE="config.delta.dryrun.json"

echo "Starting Freqtrade in DRY-RUN mode..."

# Ensure whitelist exists
if [ ! -f "user_data/pairlists/whitelist.delta.json" ]; then
    echo "Whitelist not found. Attempting to generate..."
    ./scripts/update_markets_and_whitelist.sh
fi

docker compose up -d

echo "Container started."
echo "View logs: docker compose logs -f"
