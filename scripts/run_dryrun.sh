#!/bin/bash
export FREQTRADE_CONFIG_FILE=config.delta.dryrun.json
echo "Starting dry-run with $FREQTRADE_CONFIG_FILE..."
docker compose up -d
echo "Started dry-run. Check logs with: docker compose logs -f"
