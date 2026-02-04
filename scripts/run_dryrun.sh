#!/bin/bash
export FREQTRADE_CONFIG_FILE=config.delta.dryrun.json
docker compose up -d
echo "Started dry-run with config: $FREQTRADE_CONFIG_FILE"
