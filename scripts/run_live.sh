#!/bin/bash
echo "WARNING: YOU ARE ABOUT TO START LIVE TRADING WITH REAL FUNDS."
read -p "Are you sure? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    exit 1
fi
export FREQTRADE_CONFIG_FILE=config.delta.live.json
docker compose up -d
docker compose logs -f
