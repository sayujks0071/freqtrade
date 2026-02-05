#!/bin/bash
export FREQTRADE_CONFIG_FILE=config.delta.dryrun.json
docker compose up -d
docker compose logs -f
