#!/bin/bash
set -e

# Initialize user_data directories
mkdir -p user_data/configs
mkdir -p user_data/pairlists
mkdir -p user_data/strategies/_base
mkdir -p user_data/protections
mkdir -p user_data/reports
mkdir -p user_data/logs
mkdir -p user_data/strategies_vendor

# Create __init__.py for proper package resolution
touch user_data/__init__.py
touch user_data/strategies/__init__.py
touch user_data/strategies/_base/__init__.py
touch user_data/protections/__init__.py

# Copy .env.example to .env if it doesn't exist
if [ ! -f .env ]; then
    echo "Copying .env.example to .env..."
    cp .env.example .env
else
    echo ".env already exists."
fi

# Create a default empty whitelist if it doesn't exist to prevent startup errors
if [ ! -f user_data/pairlists/whitelist.delta.json ]; then
    echo '{"exchange": {"pair_whitelist": ["BTC/USDT:USDT"]}}' > user_data/pairlists/whitelist.delta.json
fi

echo "Bootstrap complete."
