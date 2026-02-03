#!/bin/bash
set -e

# Ensure root
cd "$(dirname "$0")/.."

echo "Bootstrapping Delta Freqtrade..."

mkdir -p user_data/configs
mkdir -p user_data/pairlists
mkdir -p user_data/strategies
mkdir -p user_data/strategies/_base
mkdir -p user_data/protections
mkdir -p user_data/reports
mkdir -p user_data/logs
mkdir -p user_data/strategies_vendor

if [ ! -f .env ]; then
    echo "Creating .env from .env.example..."
    cp .env.example .env
    echo "Please edit .env with your credentials."
fi

# Ensure initial whitelist exists to prevent crash
if [ ! -f user_data/pairlists/whitelist.delta.json ]; then
    echo "Creating default whitelist..."
    # Use valid format for Delta Futures (examples)
    echo '{"exchange": {"pair_whitelist": ["BTC/USDT:USDT", "ETH/USDT:USDT"]}}' > user_data/pairlists/whitelist.delta.json
fi

echo "Bootstrap complete."
