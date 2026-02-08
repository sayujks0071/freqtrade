#!/bin/bash
set -e

echo "Bootstrapping Freqtrade Delta Stack..."

# Create directories
echo "Creating user_data directories..."
mkdir -p user_data/configs
mkdir -p user_data/reports
mkdir -p user_data/logs
mkdir -p user_data/data
mkdir -p user_data/db
mkdir -p user_data/strategies

# Copy .env if not exists
if [ ! -f .env ]; then
    echo "Copying .env.example to .env..."
    cp .env.example .env
    echo "NOTE: Please edit .env with your Delta API keys!"
else
    echo ".env already exists. Skipping copy."
fi

echo "Bootstrap complete."
echo "Next steps:"
echo "1. Edit .env with your API credentials (DELTA_API_KEY, DELTA_API_SECRET)."
echo "2. Run 'scripts/validate_exchange.sh' to verify connectivity and markets."
echo "3. Run 'scripts/run_dryrun.sh' to start the bot in dry-run mode."
