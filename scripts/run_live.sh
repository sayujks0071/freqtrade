#!/bin/bash
echo "WARNING: This will start LIVE trading on Delta Exchange."
echo "Ensure your API keys are set in .env and you have read the risk profile."
read -p "Are you sure you want to proceed? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    exit 1
fi

export FREQTRADE_CONFIG_FILE=config.delta.live.json
echo "Starting LIVE with $FREQTRADE_CONFIG_FILE..."
docker compose up -d
echo "Started LIVE trading. Check logs with: docker compose logs -f"
