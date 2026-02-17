#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$SCRIPT_DIR/.."
source "$SCRIPT_DIR/common.sh"

echo "Starting Freqtrade in DRY RUN mode ($DELTA_ENV)..."

# 1. Validate Exchange
"$SCRIPT_DIR/validate_exchange.sh"

# 2. Start Docker
export FREQTRADE_CONFIG_FILE="config.delta.dryrun.json"
echo "Configuration: $FREQTRADE_CONFIG_FILE"

docker compose up -d

echo "Freqtrade started in background."
echo "To view logs: docker compose logs -f freqtrade"
