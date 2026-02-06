#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$DIR/common.sh"

export FREQTRADE_CONFIG_FILE="config.delta.dryrun.json"

echo "Starting Freqtrade in DRY-RUN mode..."

# Check whitelist
if [ ! -f user_data/pairlists/whitelist.delta.json ]; then
    echo "Whitelist not found. Running bootstrap..."
    ./scripts/bootstrap.sh
fi

echo "Using config: $FREQTRADE_CONFIG_FILE"

# Start Docker
# We use --remove-orphans to ensure clean state
docker compose up -d --remove-orphans

echo "Container started."
echo "View logs: docker compose logs -f"
