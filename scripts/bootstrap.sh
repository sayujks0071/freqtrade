#!/bin/bash
set -e

echo "Bootstrapping Freqtrade Delta Stack..."

# Create directories
mkdir -p user_data/configs
mkdir -p user_data/reports
mkdir -p user_data/logs
mkdir -p user_data/data
mkdir -p user_data/pairlists
mkdir -p user_data/strategies/_base
mkdir -p user_data/strategies_vendor
mkdir -p user_data/db
mkdir -p user_data/protections

# Copy .env if not exists
if [ ! -f .env ]; then
    echo "Copying .env.example to .env..."
    cp .env.example .env
    echo "Please edit .env with your Delta API keys!"
else
    echo ".env already exists."
fi

# Create dummy whitelist if missing to allow startup
if [ ! -f user_data/pairlists/whitelist.delta.json ]; then
    echo "Creating dummy whitelist..."
    echo '["BTC/USDT:USDT", "ETH/USDT:USDT"]' > user_data/pairlists/whitelist.delta.json
fi

echo "Bootstrap complete."
echo "Next steps:"
echo "1. Edit .env with your API credentials."
echo "2. Run 'scripts/validate_exchange.sh' to verify connectivity and markets."
echo "3. Run 'scripts/run_dryrun.sh' to start the bot in dry-run mode."
