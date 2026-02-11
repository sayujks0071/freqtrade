#!/bin/bash
set -e

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
    echo "Creating .env from .env.example..."
    cp .env.example .env
    echo "PLEASE EDIT .env WITH YOUR CREDENTIALS!"
else
    echo ".env already exists."
fi

# Attempt to fetch markets if .env seems populated
if grep -q "DELTA_API_KEY=your_api_key_here" .env; then
    echo "WARNING: .env still has default values. Skipping market fetch."
    echo "Please edit .env and then run scripts/update_markets_and_whitelist.sh manually."
else
    echo "Attempting to fetch markets and generate whitelist..."
    ./scripts/update_markets_and_whitelist.sh || echo "WARNING: Market fetch failed. Check your API keys in .env."
fi

echo "Bootstrap complete."
echo "Next steps:"
echo "1. Edit .env with your API credentials (if not done)."
echo "2. Run 'scripts/validate_exchange.sh' to verify connectivity."
echo "3. Run 'scripts/run_dryrun.sh' to start."
