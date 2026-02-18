#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$DIR/common.sh"

export FREQTRADE_CONFIG_FILE="config.delta.dryrun.json"

echo "=== STARTING DRY-RUN TRADING ==="
echo "Environment: $DELTA_ENV ($BASE_URL)"

echo "Pre-flight checks..."
"$DIR/validate_exchange.sh"
if [ $? -ne 0 ]; then
    echo "FAIL: Validation failed. Aborting startup."
    exit 1
fi

echo "Starting Freqtrade service..."
docker compose up -d

echo "SUCCESS: Container started."
echo "View logs: docker compose logs -f"
echo "Access UI: http://localhost:8080 (User: freqtrader / Pass: SuperSecurePassword123!)"
