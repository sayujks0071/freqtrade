#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$DIR/common.sh"

export FREQTRADE_CONFIG_FILE="config.delta.dryrun.json"

echo "Starting Freqtrade in DRY-RUN mode..."

# Ensure we are in the root
cd "$(dirname "$0")/.."

# Check whitelist
if [ ! -f user_data/pairlists/whitelist.delta.json ]; then
    echo "Whitelist not found. Running bootstrap..."
    ./scripts/bootstrap.sh
fi

echo "Starting Freqtrade in Docker..."
docker compose up -d --remove-orphans
echo "Container started. View logs with: docker compose logs -f"
