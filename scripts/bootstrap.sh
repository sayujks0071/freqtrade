#!/bin/bash
set -e

echo "Bootstrapping Freqtrade Delta Stack..."

# Get the directory of the script
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
ROOT_DIR="$(dirname "$DIR")"

# Create necessary directories
echo "Creating directories in user_data/..."
mkdir -p "$ROOT_DIR/user_data/configs"
mkdir -p "$ROOT_DIR/user_data/pairlists"
mkdir -p "$ROOT_DIR/user_data/reports"
mkdir -p "$ROOT_DIR/user_data/logs"
mkdir -p "$ROOT_DIR/user_data/data"

# Copy .env.example to .env if it doesn't exist
if [ ! -f "$ROOT_DIR/.env" ]; then
    echo "Copying .env.example to .env..."
    cp "$ROOT_DIR/.env.example" "$ROOT_DIR/.env"
    echo "PLEASE EDIT .env WITH YOUR DELTA API CREDENTIALS!"
else
    echo ".env already exists. skipping copy."
fi

echo "Bootstrap complete."
