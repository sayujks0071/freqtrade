#!/bin/bash
set -e

echo "Bootstrapping Delta Exchange Freqtrade Stack..."

# Create necessary directories
echo "Creating directories..."
mkdir -p user_data/configs
mkdir -p user_data/data
mkdir -p user_data/db
mkdir -p user_data/logs
mkdir -p user_data/pairlists
mkdir -p user_data/reports
mkdir -p user_data/strategies/_base
mkdir -p user_data/strategies_vendor

# Copy .env if not exists
if [ ! -f .env ]; then
    echo "Creating .env from .env.example..."
    cp .env.example .env
    echo "PLEASE EDIT .env WITH YOUR CREDENTIALS!"
else
    echo ".env already exists."
fi

# Create dummy whitelist if missing to allow startup
if [ ! -f user_data/pairlists/whitelist.delta.json ]; then
    echo "Creating dummy whitelist to allow initial startup..."
    echo '{"exchange": {"pair_whitelist": ["BTC/USDT:USDT", "ETH/USDT:USDT"]}}' > user_data/pairlists/whitelist.delta.json
fi

# Make scripts executable
chmod +x scripts/*.sh
chmod +x tools/*.py

echo "Bootstrap complete."
echo ""
echo "Next steps:"
echo "1. Edit .env with your API credentials and settings."
echo "2. Run 'scripts/validate_exchange.sh' to verify connectivity and markets."
echo "3. Run 'scripts/run_dryrun.sh' to start the bot in dry-run mode."
