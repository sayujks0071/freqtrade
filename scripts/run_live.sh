#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$DIR/common.sh"

export FREQTRADE_CONFIG_FILE="config.delta.live.json"

echo "!!! WARNING: STARTING LIVE TRADING !!!"
echo "You are about to trade with REAL FUNDS on Delta ($DELTA_ENV)."
echo "Ensure you have tested your strategy thoroughly in dry-run mode."
echo "Press 'y' to continue, any other key to abort."
read -r response
if [[ ! "$response" =~ ^([yY][eE][sS]|[yY])$ ]]
then
    echo "Aborted."
    exit 1
fi

echo "Pre-flight checks..."
"$DIR/validate_exchange.sh"
if [ $? -ne 0 ]; then
    echo "FAIL: Validation failed. Aborting startup."
    exit 1
fi

echo "Switching to LIVE configuration..."
echo "Starting Freqtrade service..."
docker compose up -d

echo "SUCCESS: LIVE TRADING STARTED."
echo "View logs immediately: docker compose logs -f"
echo "Monitor UI at http://localhost:8080"
