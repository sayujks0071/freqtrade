#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$SCRIPT_DIR/.."
source "$SCRIPT_DIR/common.sh"

echo "********************************************"
echo "WARNING: STARTING FREQTRADE IN LIVE MODE!"
echo "Environment: $DELTA_ENV"
echo "This will use REAL MONEY."
echo "********************************************"

read -p "Are you sure you want to proceed? (yes/no) " confirmation
if [ "$confirmation" != "yes" ]; then
    echo "Aborted."
    exit 1
fi

echo "Starting Freqtrade in LIVE mode ($DELTA_ENV)..."

# 1. Validate Exchange
"$SCRIPT_DIR/validate_exchange.sh"

# 2. Start Docker
export FREQTRADE_CONFIG_FILE="config.delta.live.json"
echo "Configuration: $FREQTRADE_CONFIG_FILE"

docker compose up -d

echo "Freqtrade started in background (LIVE)."
echo "To view logs: docker compose logs -f freqtrade"
