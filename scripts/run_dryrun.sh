#!/bin/bash
set -e
cd "$(dirname "$0")/.."

# Load .env
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

echo "Starting Freqtrade DRY-RUN on Delta ($DELTA_ENV)..."

# Ensure whitelist exists
if [ ! -f user_data/pairlists/whitelist.delta.json ]; then
    echo "WARNING: Whitelist not found. Creating empty one."
    mkdir -p user_data/pairlists
    echo '{"exchange": {"pair_whitelist": []}}' > user_data/pairlists/whitelist.delta.json
fi

export FREQTRADE_CONFIG_FILE="config.delta.dryrun.json"

docker compose up -d

echo "Dry-run started."
echo "View logs: docker compose logs -f"
