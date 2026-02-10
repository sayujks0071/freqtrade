#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$DIR/common.sh"

echo "Starting Freqtrade in DRY-RUN mode ($DELTA_ENV)..."

# Ensure whitelist exists
WHITELIST_FILE="user_data/pairlists/whitelist.delta.json"
if [ ! -f "$WHITELIST_FILE" ]; then
    echo "Whitelist ($WHITELIST_FILE) not found."
    echo "Running validation to generate it..."
    "$DIR/validate_exchange.sh"
    if [ ! -f "$WHITELIST_FILE" ]; then
        echo "Failed to generate whitelist. Aborting."
        exit 1
    fi
fi

# Set Config for docker-compose
export FREQTRADE_CONFIG_FILE="config.delta.dryrun.json"

# Start container
docker compose up -d

echo "Container started."
echo "View logs: docker compose logs -f"
