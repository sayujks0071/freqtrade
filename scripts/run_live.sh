#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$DIR/common.sh"

echo "!!! WARNING: PREPARING TO START LIVE TRADING ($DELTA_ENV) !!!"

# Ensure whitelist exists
WHITELIST_FILE="user_data/pairlists/whitelist.delta.json"
if [ ! -f "$WHITELIST_FILE" ]; then
    echo "Whitelist ($WHITELIST_FILE) not found."
    echo "Please run scripts/validate_exchange.sh first or bootstrap."
    exit 1
fi

echo "Configuration: config.delta.live.json"
echo "Whitelist: whitelist.delta.json"

# Just display info, common.sh already handled URL logic
echo "Using Delta Environment: $DELTA_ENV"

read -p "Are you absolutely sure you want to trade real money? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 1
fi

# Set Config for docker-compose
export FREQTRADE_CONFIG_FILE="config.delta.live.json"

# Start container
docker compose up -d

echo "LIVE TRADING Container started."
echo "View logs: docker compose logs -f"
