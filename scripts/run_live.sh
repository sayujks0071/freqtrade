#!/bin/bash
set -e
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$DIR/common.sh"

echo "Running Validation..."
if ! "$DIR/validate_exchange.sh"; then
    echo "Validation Failed. Aborting start."
    exit 1
fi

echo "!!! WARNING: YOU ARE ABOUT TO START LIVE TRADING !!!"
echo "This will use REAL money on $DELTA_ENV."
echo "Config: user_data/configs/config.delta.live.json"
read -p "Are you absolutely sure? (Type 'YES' to confirm): " confirm
if [ "$confirm" != "YES" ]; then
    echo "Aborted."
    exit 1
fi

echo "Switching to LIVE config..."
cp user_data/configs/config.delta.live.json user_data/config.json

echo "Starting Freqtrade in Docker (LIVE)..."
docker compose up -d --remove-orphans
docker compose logs -f
