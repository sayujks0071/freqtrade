#!/bin/bash
set -e

echo "Bootstrapping Freqtrade Delta Stack..."

# Create directories
mkdir -p user_data/configs
mkdir -p user_data/logs
mkdir -p user_data/pairlists
mkdir -p user_data/reports
mkdir -p user_data/data
mkdir -p user_data/strategies
mkdir -p user_data/db
mkdir -p tools

# Check for essential tools
if [ ! -f "tools/generate_whitelist.py" ]; then
    echo "WARNING: tools/generate_whitelist.py is missing!"
    echo "This file is required for market validation."
else
    echo "Verified tools/generate_whitelist.py exists."
fi

# Copy .env if not exists
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        echo "Copying .env.example to .env..."
        cp .env.example .env
        echo "Please edit .env with your Delta API keys!"
    else
        echo "WARNING: .env.example not found!"
    fi
else
    echo ".env already exists."
fi

# Make scripts executable
chmod +x scripts/*.sh

echo "Bootstrap complete."
echo "Next steps:"
echo "1. Edit .env with your API credentials (DELTA_API_KEY, DELTA_API_SECRET)."
echo "2. Run 'scripts/validate_exchange.sh' to verify markets and generate whitelist."
echo "3. Run 'scripts/run_dryrun.sh' to start the bot."
