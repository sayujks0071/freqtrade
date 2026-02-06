#!/bin/bash
set -e

echo "Bootstrapping Freqtrade Delta Stack..."

# Create directories
mkdir -p user_data/configs user_data/reports user_data/logs user_data/data user_data/pairlists user_data/db

# Copy .env if not exists
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        echo "Copying .env.example to .env..."
        cp .env.example .env
        echo "PLEASE EDIT .env WITH YOUR DELTA API KEYS!"
    else
        echo "Warning: .env.example not found. Creating empty .env..."
        touch .env
    fi
else
    echo ".env already exists. Skipping copy."
fi

# Create dummy whitelist if missing to allow startup (needed for validation scripts sometimes)
if [ ! -f user_data/pairlists/whitelist.delta.json ]; then
    echo "Creating initial whitelist.delta.json..."
    # Minimal whitelist for Delta Futures with CORRECT structure
    echo '{"exchange": {"pair_whitelist": ["BTC/USDT:USDT", "ETH/USDT:USDT"]}}' > user_data/pairlists/whitelist.delta.json
fi

echo "Bootstrap complete."
echo "Next steps:"
echo "1. Edit .env with your API credentials."
echo "2. Run 'scripts/validate_exchange.sh' to verify connectivity and markets."
echo "3. Run 'scripts/run_dryrun.sh' to start the bot in dry-run mode."
