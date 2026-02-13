#!/bin/bash
set -e
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$DIR/common.sh"

echo "Running Validation..."
if ! "$DIR/validate_exchange.sh"; then
    echo "Validation Failed. Aborting start."
    exit 1
fi

echo "Switching to DRY-RUN config..."
cp user_data/configs/config.delta.dryrun.json user_data/config.json

echo "Starting Freqtrade in Docker (DRY-RUN)..."
docker compose up -d --remove-orphans
docker compose logs -f
