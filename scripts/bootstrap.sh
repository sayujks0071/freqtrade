#!/bin/bash
set -e

echo "Bootstrapping Freqtrade Delta Stack..."

# Create directories
mkdir -p user_data/configs
mkdir -p user_data/logs
mkdir -p user_data/pairlists
mkdir -p user_data/reports
mkdir -p user_data/data
mkdir -p user_data/strategies/_base
mkdir -p user_data/strategies_vendor
mkdir -p user_data/db

# Copy .env if not exists
if [ ! -f .env ]; then
    echo "Copying .env.example to .env..."
    cp .env.example .env
    echo "PLEASE EDIT .env WITH YOUR DELTA API KEYS AND ENV!"
else
    echo ".env already exists. Ensure it has correct keys."
fi

# Create dummy whitelist if missing to allow first startup
if [ ! -f user_data/pairlists/whitelist.delta.json ]; then
    echo "Creating dummy whitelist..."
    echo '{"exchange": {"pair_whitelist": ["BTC/USDT:USDT", "ETH/USDT:USDT"]}}' > user_data/pairlists/whitelist.delta.json
fi

echo "Bootstrap complete."
echo "Next steps:"
echo "1. Edit .env with your API credentials."
echo "2. Run 'scripts/validate_exchange.sh' to verify connectivity and markets."
echo "3. Run 'scripts/run_dryrun.sh' to start the bot in dry-run mode."
