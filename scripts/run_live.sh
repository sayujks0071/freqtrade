#!/bin/bash
set -e
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR/.."
source "$DIR/common.sh"

echo "!!! WARNING: STARTING LIVE TRADING !!!"
echo "You are about to trade with REAL FUNDS on Delta Exchange."
echo "Config: user_data/configs/config.delta.live.json"
echo
read -p "Are you absolutely sure? (Type 'yes' to confirm): " confirm
if [[ "$confirm" != "yes" ]]; then
    echo "Aborted."
    exit 1
fi

echo "Running Preflight Checks..."
if ./scripts/validate_exchange.sh; then
    echo "Preflight Checks Passed."
else
    echo "Preflight Checks Failed. Aborting."
    exit 1
fi

# Check whitelist
WHITELIST_ARG=""
if [ -f "user_data/pairlists/whitelist.delta.json" ]; then
    echo "Found whitelist.delta.json, including it..."
    WHITELIST_ARG=" --config /freqtrade/user_data/pairlists/whitelist.delta.json"
fi

export FREQTRADE_CONFIG_FILE="config.delta.live.json${WHITELIST_ARG}"

echo "Starting Freqtrade in LIVE mode..."
docker compose up -d

echo "Container started in LIVE mode."
echo "View logs: docker compose logs -f"
