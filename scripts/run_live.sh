#!/bin/bash
source "$(dirname "$0")/common.sh"

echo "****************************************"
echo "WARNING: STARTING LIVE TRADING ON $DELTA_ENV"
echo "REAL FUNDS ARE AT RISK."
echo "****************************************"

preflight_check

echo "Using config: config.delta.live.json"

read -p "Are you sure you want to proceed? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 1
fi

export FREQTRADE_CONFIG_FILE=config.delta.live.json

docker compose up -d

echo "Container started in LIVE mode."
echo "View logs with: docker compose logs -f freqtrade"
echo "Access UI at: http://localhost:8080"
