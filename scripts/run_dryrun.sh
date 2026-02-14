#!/bin/bash
set -e
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR/.."
source "$DIR/common.sh"

echo "Running Preflight Checks..."
if ./scripts/validate_exchange.sh; then
    echo "Preflight Checks Passed."
else
    echo "Preflight Checks Failed. Aborting."
    exit 1
fi

echo "Starting Freqtrade in DRY-RUN mode..."

# Check whitelist and construct config argument
WHITELIST_ARG=""
if [ -f "user_data/pairlists/whitelist.delta.json" ]; then
    echo "Found whitelist.delta.json, including it..."
    WHITELIST_ARG=" --config /freqtrade/user_data/pairlists/whitelist.delta.json"
fi

export FREQTRADE_CONFIG_FILE="config.delta.dryrun.json${WHITELIST_ARG}"

docker compose up -d

echo "Container started in DRY-RUN mode."
echo "View logs: docker compose logs -f"
