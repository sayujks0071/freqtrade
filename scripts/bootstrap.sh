#!/bin/bash
set -e

# Create directories
mkdir -p user_data/configs
mkdir -p user_data/pairlists
mkdir -p user_data/strategies
mkdir -p user_data/strategies/_base
mkdir -p user_data/strategies_vendor
mkdir -p user_data/reports
mkdir -p user_data/logs
mkdir -p user_data/protections

# Copy env
if [ ! -f .env ]; then
    echo "Copying .env.example to .env"
    cp .env.example .env
else
    echo ".env already exists, skipping copy."
fi

# Make scripts executable
chmod +x scripts/*.sh 2>/dev/null || true

echo "Bootstrap complete."
