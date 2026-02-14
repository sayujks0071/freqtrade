#!/bin/bash
set -e

# Setup user_data directory structure
echo "Creating user_data directory structure..."
mkdir -p user_data/configs
mkdir -p user_data/pairlists
mkdir -p user_data/strategies
mkdir -p user_data/logs
mkdir -p user_data/reports
mkdir -p user_data/protections
mkdir -p user_data/data
mkdir -p user_data/notebooks
mkdir -p user_data/backtest_results

# Check for .env file
if [ ! -f .env ]; then
    echo ".env not found. Copying from .env.example..."
    cp .env.example .env
    echo "Please edit .env with your configuration."
fi

# Ensure initial whitelist exists if not present
DELTA_ENV=${DELTA_ENV:-india_testnet}
WHITELIST_FILE="user_data/pairlists/whitelist.delta.${DELTA_ENV}.json"
if [ ! -f "$WHITELIST_FILE" ]; then
    echo "Creating dummy whitelist for $DELTA_ENV..."
    echo '{"exchange": {"pair_whitelist": ["BTC/USDT:USDT"]}}' > "$WHITELIST_FILE"
fi

echo "Bootstrap complete."
