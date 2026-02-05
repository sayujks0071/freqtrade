#!/bin/bash
set -e

# Ensure root
cd "$(dirname "$0")/.."

echo "Bootstrapping Delta Exchange Freqtrade Stack..."

# Create directories
mkdir -p user_data/configs
mkdir -p user_data/logs
mkdir -p user_data/pairlists
mkdir -p user_data/reports
mkdir -p user_data/strategies/_base
mkdir -p user_data/strategies_vendor
mkdir -p user_data/db
mkdir -p user_data/data

# Copy env if missing
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        echo "Creating .env from .env.example..."
        cp .env.example .env
        echo "PLEASE EDIT .env WITH YOUR CREDENTIALS!"
    else
        echo "WARNING: .env.example not found!"
    fi
else
    echo ".env already exists."
fi

# Create dummy whitelist if missing to allow startup before first market refresh
if [ ! -f user_data/pairlists/whitelist.delta.json ]; then
    echo "Creating dummy whitelist..."
    echo '{"exchange": {"pair_whitelist": ["BTC/USDT:USDT", "ETH/USDT:USDT"]}}' > user_data/pairlists/whitelist.delta.json
fi

echo "Bootstrap complete."
echo "Next steps:"
echo "1. Edit .env with your API credentials."
echo "2. Run 'scripts/validate_exchange.sh' to verify connectivity and markets."
echo "3. Run 'scripts/update_markets_and_whitelist.sh' to generate real whitelist."
echo "4. Run 'scripts/run_dryrun.sh' to start the bot."
