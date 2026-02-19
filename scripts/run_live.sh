#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$DIR/common.sh"

echo "=========================================="
echo "WARNING: Starting LIVE TRADING Mode ($DELTA_ENV)!"
echo "Real money will be used."
echo "=========================================="

echo "Running Preflight Checks..."
# Run full validation including time sync and market check
if ! "$DIR/validate_exchange.sh"; then
    echo "ERROR: Preflight checks failed! Aborting startup."
    exit 1
fi

echo "Preflight Passed."
echo "Press Ctrl+C to cancel in 5 seconds..."
sleep 5

export FREQTRADE_CONFIG_FILE="config.delta.live.json"

# Check if config exists
if [ ! -f "user_data/configs/$FREQTRADE_CONFIG_FILE" ]; then
    echo "Error: Config file user_data/configs/$FREQTRADE_CONFIG_FILE not found!"
    exit 1
fi

docker compose up -d
echo "Bot started in LIVE mode. View logs with: docker compose logs -f"
