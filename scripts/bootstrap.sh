#!/bin/bash
set -e

echo "Bootstrapping Freqtrade Delta Stack..."

# Create directories
mkdir -p user_data/configs
mkdir -p user_data/logs
mkdir -p user_data/pairlists
mkdir -p user_data/reports
mkdir -p user_data/data
mkdir -p user_data/db
mkdir -p user_data/strategies
mkdir -p user_data/strategies/_base

# Copy .env if not exists
if [ ! -f .env ]; then
    echo "Copying .env.example to .env..."
    cp .env.example .env
    echo "Created .env file."
else
    echo ".env file already exists."
fi

# Make scripts executable
chmod +x scripts/*.sh

echo "Bootstrap complete."
echo "Please edit .env with your Delta API keys!"
echo "Then run: ./scripts/run_dryrun.sh"
