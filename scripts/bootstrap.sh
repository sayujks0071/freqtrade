#!/bin/bash
set -e

# Create directories
mkdir -p user_data/configs
mkdir -p user_data/reports

# Setup .env
if [ ! -f .env ]; then
    echo "Copying .env.example to .env..."
    cp .env.example .env
    echo "Please edit .env with your Delta Exchange credentials."
else
    echo ".env already exists."
fi

echo "Bootstrap complete. Next steps:"
echo "1. Edit .env with your API keys and DELTA_ENV."
echo "2. Run 'bash scripts/validate_exchange.sh' to verify connection and markets."
echo "3. Run 'bash scripts/run_dryrun.sh' to start the bot."
