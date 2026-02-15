#!/bin/bash
set -e

# Get the directory of the script
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$DIR/common.sh"

echo "=== STARTING FREQTRADE IN LIVE TRADING MODE ON DELTA ($DELTA_ENV) ==="
echo "!!! WARNING: THIS WILL USE REAL FUNDS !!!"
echo "!!! MAKE SURE YOU KNOW WHAT YOU ARE DOING !!!"

read -p "Are you sure you want to trade REAL money? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]
then
    echo "Aborted."
    exit 1
fi

# Confirm again
read -p "Confirm again: START LIVE TRADING? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]
then
    echo "Aborted."
    exit 1
fi

# Run Validation Steps
echo "Running pre-flight validation..."
"$DIR/validate_exchange.sh"

# Set Config File for Docker Compose
export FREQTRADE_CONFIG_FILE="config.delta.live.json"

echo "Starting Container in LIVE MODE..."
docker compose up -d

echo "=== Freqtrade LIVE Trading Started ==="
echo "UI: http://localhost:8080"
echo "Logs: docker compose logs -f"
