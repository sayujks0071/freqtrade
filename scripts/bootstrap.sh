#!/bin/bash
set -e

# Create user_data directories
mkdir -p user_data/configs
mkdir -p user_data/data
mkdir -p user_data/logs
mkdir -p user_data/reports
mkdir -p user_data/strategies/_base
mkdir -p user_data/protections
mkdir -p user_data/pairlists
mkdir -p tools

# Create initial whitelist if not exists
if [ ! -f user_data/pairlists/whitelist.delta.json ]; then
    echo '["BTC/USDT:USDT", "ETH/USDT:USDT"]' > user_data/pairlists/whitelist.delta.json
fi

echo "Directories initialized."
