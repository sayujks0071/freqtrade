#!/bin/bash
set -e

# Ensure we are in the root
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

# Copy env if missing
if [ ! -f .env ]; then
    echo "Creating .env from .env.example..."
    cp .env.example .env
    echo "PLEASE EDIT .env WITH YOUR CREDENTIALS!"
else
    echo ".env already exists."
fi

# Ensure scripts are executable
chmod +x scripts/*.sh

echo "Bootstrap complete."
echo "Next steps:"
echo "1. Edit .env with your API credentials."
echo "2. Run 'scripts/validate_exchange.sh' to verify connectivity and markets."
echo "3. Run 'scripts/run_dryrun.sh' to start the bot in dry-run mode."
