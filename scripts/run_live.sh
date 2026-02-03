#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$DIR/common.sh"

echo "=== Delta Freqtrade (LIVE) ==="
echo "!!! WARNING: STARTING IN LIVE TRADING MODE !!!"
echo "!!! REAL MONEY WILL BE USED !!!"
echo "Exchange: Delta ($DELTA_ENV)"

read -p "Are you sure? (Type 'yes' to confirm): " confirm
if [ "$confirm" != "yes" ]; then
    echo "Aborted."
    exit 1
fi

# Preflight Check
echo "Running Preflight Checks..."
"$DIR/validate_exchange.sh"
if [ $? -ne 0 ]; then
    echo "PREFLIGHT FAILED. Aborting."
    exit 1
fi

echo "Starting Freqtrade in LIVE mode..."
echo "Using config: config.delta.live.json"

export FREQTRADE_CONFIG_FILE="config.delta.live.json"

docker compose up -d

echo "Container started."
echo "View logs: docker compose logs -f"
