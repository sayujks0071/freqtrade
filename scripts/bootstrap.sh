#!/bin/bash
set -e
cd "$(dirname "$0")/.."

# Source common
source scripts/common.sh

echo "Bootstrapping Freqtrade Delta Stack..."

# Create directories
echo "Creating directories..."
mkdir -p user_data/configs
mkdir -p user_data/reports
mkdir -p user_data/logs
mkdir -p user_data/data
mkdir -p user_data/db
mkdir -p user_data/pairlists
mkdir -p user_data/strategies/_base
mkdir -p user_data/strategies_vendor

# Copy .env if not exists
if [ ! -f .env ]; then
    echo "Copying .env.example to .env..."
    cp .env.example .env
    echo "PLEASE EDIT .env WITH YOUR CREDENTIALS!"
else
    echo ".env already exists."
fi

# Create dummy whitelist if missing to allow startup
# This is a valid Freqtrade config snippet
WHITELIST_FILE="user_data/pairlists/whitelist.delta.json"
if [ ! -f "$WHITELIST_FILE" ]; then
    echo "Creating initial whitelist..."
    # Minimal whitelist to ensure valid JSON config
    echo '{
    "exchange": {
        "pair_whitelist": [
            "BTC/USDT:USDT",
            "ETH/USDT:USDT"
        ]
    }
}' > "$WHITELIST_FILE"
fi

echo "Bootstrap complete."
echo "Next steps:"
echo "1. Edit .env with your API credentials."
echo "2. Run 'scripts/validate_exchange.sh' to verify connectivity and markets."
echo "3. Run 'scripts/run_dryrun.sh' to start the bot in dry-run mode."
