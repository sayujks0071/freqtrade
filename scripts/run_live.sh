#!/bin/bash
set -e
cd "$(dirname "$0")/.."

source scripts/common.sh

echo "*****************************************************"
echo "*  WARNING: STARTING LIVE TRADING ON DELTA EXCHANGE  *"
echo "*  Env: $DELTA_ENV                                   *"
echo "*****************************************************"
echo ""

read -p "Are you sure you want to proceed? (Type 'YES' to confirm): " confirm
if [[ "$confirm" != "YES" ]]; then
    echo "Aborted."
    exit 1
fi

echo "Running pre-flight checks..."
./scripts/validate_exchange.sh

# Set config file
export FREQTRADE_CONFIG_FILE=config.delta.live.json

echo "Starting container (LIVE)..."
docker compose up -d

echo "Container started (LIVE). Tailing logs..."
docker compose logs -f freqtrade
