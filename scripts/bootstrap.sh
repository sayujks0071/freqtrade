#!/bin/bash
set -e

echo "Bootstrapping Delta Exchange Freqtrade environment..."

# Create directories
mkdir -p user_data/configs
mkdir -p user_data/reports
mkdir -p user_data/logs
mkdir -p user_data/data/delta
mkdir -p user_data/db
mkdir -p user_data/strategies
mkdir -p user_data/strategies_vendor
mkdir -p user_data/protections
mkdir -p user_data/pairlists

# Create initial whitelist if missing
if [ ! -f user_data/pairlists/whitelist.delta.json ]; then
  echo "Creating initial whitelist.delta.json..."
  echo '["BTC/USDT:USDT", "ETH/USDT:USDT"]' > user_data/pairlists/whitelist.delta.json
fi

# Copy .env.example to .env if not exists
if [ ! -f .env ]; then
  if [ -f .env.example ]; then
    echo "Copying .env.example to .env..."
    cp .env.example .env
  else
    echo "Warning: .env.example not found."
  fi
else
  echo ".env already exists."
fi

# Set permissions (optional, but good practice)
chmod +x scripts/*.sh 2>/dev/null || true

echo "Bootstrap complete. Please edit .env with your Delta Exchange credentials."
