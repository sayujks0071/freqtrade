#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$DIR/common.sh"

export FREQTRADE_CONFIG_FILE="config.delta.live.json"

echo "!!! WARNING: STARTING LIVE TRADING ON DELTA ($DELTA_ENV) !!!"
echo "This involves REAL MONEY."
echo "Config: $FREQTRADE_CONFIG_FILE"

if [ -t 0 ]; then
    read -p "Are you ABSOLUTELY sure? (Type 'yes' to confirm): " confirm
    if [ "$confirm" != "yes" ]; then
        echo "Aborted."
        exit 1
    fi
else
    echo "Non-interactive mode detected. Ensure you know what you are doing."
fi

# Pre-flight check
if [ ! -f "user_data/pairlists/whitelist.delta.json" ]; then
    echo "ERROR: Whitelist file not found!"
    echo "You must run 'scripts/validate_exchange.sh' first."
    exit 1
fi

docker compose up -d

echo "LIVE TRADING STARTED."
echo "View logs: docker compose logs -f"
