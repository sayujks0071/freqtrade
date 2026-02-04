#!/bin/bash
read -p "Are you sure you want to start LIVE trading? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]
then
    exit 1
fi
export FREQTRADE_CONFIG_FILE=config.delta.live.json
docker compose up -d
echo "Started LIVE trading with config: $FREQTRADE_CONFIG_FILE"
