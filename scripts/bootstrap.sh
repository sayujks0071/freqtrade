#!/bin/bash
set -e

echo "Bootstrapping Freqtrade Delta Stack..."

# Create necessary directories
DIRS=(
    "user_data/configs"
    "user_data/logs"
    "user_data/reports"
    "user_data/pairlists"
    "user_data/strategies/_base"
    "user_data/strategies_vendor"
    "user_data/data"
    "user_data/db"
)

for dir in "${DIRS[@]}"; do
    if [ ! -d "$dir" ]; then
        echo "Creating $dir..."
        mkdir -p "$dir"
    else
        echo "Directory $dir exists."
    fi
done

# Copy .env if not exists
if [ ! -f .env ]; then
    echo "Copying .env.example to .env..."
    cp .env.example .env
    echo "PLEASE EDIT .env WITH YOUR CREDENTIALS!"
else
    echo ".env already exists."
fi

# Create a dummy whitelist if missing to prevent startup errors before first refresh
if [ ! -f user_data/pairlists/whitelist.delta.json ]; then
    echo "Creating dummy whitelist..."
    # Ensure directory exists just in case
    mkdir -p user_data/pairlists
    echo '{"exchange": {"pair_whitelist": ["BTC/USDT:USDT", "ETH/USDT:USDT"]}}' > user_data/pairlists/whitelist.delta.json
fi

# Ensure scripts are executable
chmod +x scripts/*.sh 2>/dev/null || true

echo "Bootstrap complete."
echo "Next steps:"
echo "1. Edit .env with your API credentials."
echo "2. Run 'scripts/validate_exchange.sh' (after setup) to verify connectivity."
echo "3. Run 'scripts/run_dryrun.sh' to start."
