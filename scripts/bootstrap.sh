#!/bin/bash
set -e

echo "Bootstrapping Delta Exchange Freqtrade Stack..."

# Create directories
mkdir -p user_data/logs
mkdir -p user_data/pairlists
mkdir -p user_data/reports
mkdir -p user_data/strategies/_base
mkdir -p user_data/strategies_vendor
mkdir -p user_data/db

# Copy env if missing
if [ ! -f .env ]; then
    echo "Creating .env from .env.example..."
    cp .env.example .env
    echo "PLEASE EDIT .env WITH YOUR CREDENTIALS!"
else
    echo ".env already exists."
fi

# Create dummy whitelist if missing to allow startup
if [ ! -f user_data/pairlists/whitelist.delta.json ]; then
    echo "Creating dummy whitelist..."
    echo '{"exchange": {"pair_whitelist": ["BTC/USDT:USDT", "ETH/USDT:USDT"]}}' > user_data/pairlists/whitelist.delta.json
fi

echo "Bootstrap complete."
