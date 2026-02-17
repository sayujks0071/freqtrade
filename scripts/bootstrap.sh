#!/bin/bash
set -e

# Base directory
BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
USER_DATA="$BASE_DIR/user_data"

echo "Bootstrapping Freqtrade setup for Delta Exchange..."

# Create directories
mkdir -p "$USER_DATA/configs"
mkdir -p "$USER_DATA/logs"
mkdir -p "$USER_DATA/reports"
mkdir -p "$USER_DATA/pairlists"
mkdir -p "$USER_DATA/strategies/_base"
mkdir -p "$USER_DATA/strategies_vendor"
mkdir -p "$USER_DATA/protections"

# Copy .env if not exists
if [ ! -f "$BASE_DIR/.env" ]; then
    echo "Copying .env.example to .env..."
    cp "$BASE_DIR/.env.example" "$BASE_DIR/.env"
else
    echo ".env already exists, skipping copy."
fi

# Create a dummy whitelist if it doesn't exist to prevent crash
WHITELIST_FILE="$USER_DATA/pairlists/whitelist.delta.json"
if [ ! -f "$WHITELIST_FILE" ]; then
    echo "Creating initial empty whitelist..."
    echo '["BTC/USDT:USDT"]' > "$WHITELIST_FILE"
fi

# Make scripts executable
chmod +x "$BASE_DIR/scripts/"*.sh 2>/dev/null || true

echo "Bootstrap complete. Please edit .env with your credentials."
