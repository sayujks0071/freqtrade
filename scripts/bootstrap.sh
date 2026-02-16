#!/bin/bash

# Ensure we are in the repo root
cd "$(dirname "$0")/.."

echo "Initializing user_data directory..."
mkdir -p user_data/configs
mkdir -p user_data/reports
mkdir -p user_data/logs
mkdir -p user_data/pairlists

if [ ! -f .env ]; then
    echo "Creating .env from .env.example..."
    cp .env.example .env
    echo ".env created. Please edit it with your Delta Exchange credentials."
else
    echo ".env already exists. Skipping creation."
fi

# Ensure config files exist (they should be part of the repo now, but just in case)
if [ ! -f user_data/configs/config.delta.dryrun.json ]; then
    echo "WARNING: user_data/configs/config.delta.dryrun.json is missing!"
fi

if [ ! -f user_data/pairlists/whitelist.delta.json ]; then
    echo "Creating empty whitelist.delta.json..."
    echo '{"exchange": {"pair_whitelist": []}}' > user_data/pairlists/whitelist.delta.json
fi

echo "Bootstrap complete."
echo "Next steps:"
echo "1. Edit .env with your API keys."
echo "2. Run scripts/validate_exchange.sh to verify connection and markets."
echo "3. Run scripts/run_dryrun.sh to start the bot."
