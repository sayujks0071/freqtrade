#!/bin/bash
set -e

# Ensure root
cd "$(dirname "$0")/.."

# Create user_data directories
mkdir -p user_data/configs
mkdir -p user_data/strategies/_base
mkdir -p user_data/reports
mkdir -p user_data/logs
mkdir -p user_data/pairlists
mkdir -p user_data/protections
mkdir -p user_data/strategies_vendor

# Copy .env if not exists
if [ ! -f .env ]; then
    echo "Creating .env from .env.example..."
    cp .env.example .env
fi

# Touch default whitelist to avoid docker errors before refresh
if [ ! -f user_data/pairlists/whitelist.delta.json ]; then
    echo "Creating empty whitelist..."
    echo '{"exchange": {"pair_whitelist": []}}' > user_data/pairlists/whitelist.delta.json
fi

echo "Environment initialized."
