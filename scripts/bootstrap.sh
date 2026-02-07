#!/bin/bash
set -e

# Ensure directories exist
mkdir -p user_data/configs user_data/reports user_data/logs user_data/data user_data/strategies

# Check if .env exists, if not, copy from .env.example
if [ ! -f .env ]; then
    echo "Creating .env from .env.example..."
    cp .env.example .env
fi

echo "Environment initialized."
echo "Please edit .env to add your API keys if you haven't already."
echo "Then, run ./scripts/validate_exchange.sh to validate and generate whitelist."
