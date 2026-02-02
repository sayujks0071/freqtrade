#!/bin/bash
set -e
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$DIR/common.sh"

echo "--------------------------------------------------"
echo "Starting Freqtrade - LIVE TRADING ($DELTA_ENV)"
echo "WARNING: REAL MONEY AT RISK."
echo "--------------------------------------------------"

# Confirmation
read -p "Are you sure you want to start LIVE trading? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 1
fi

export FREQTRADE_CONFIG_FILE="config.delta.live.json"

# Run Pre-flight Checks
"$DIR/validate_exchange.sh"

echo "Starting container..."
docker compose up -d

echo "Logs:"
docker compose logs -f freqtrade
