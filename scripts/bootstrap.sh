#!/bin/bash
set -e

echo "Bootstrapping Freqtrade Delta Stack..."

# Create directories
mkdir -p user_data/configs user_data/reports user_data/logs user_data/data
mkdir -p user_data/pairlists
mkdir -p user_data/strategies/_base
mkdir -p user_data/strategies_vendor
mkdir -p user_data/db

# Copy .env if not exists
if [ ! -f .env ]; then
    echo "Creating .env from .env.example..."
    cp .env.example .env
    echo "PLEASE EDIT .env WITH YOUR CREDENTIALS!"
else
    echo ".env already exists."
fi

# Create dummy whitelist if missing to allow startup
if [ ! -f user_data/pairlists/whitelist.delta.json ]; then
    echo "Creating dummy whitelist..."
    echo '{"exchange": {"pair_whitelist": ["BTC/USDT:USDT", "ETH/USDT:USDT"]}}' > user_data/pairlists/whitelist.delta.json
fi

# Function to setup config with random secrets
setup_config() {
    local config_file="$1"
    local example_file="${config_file/.json/.example.json}"

    if [ ! -f "$config_file" ]; then
        if [ -f "$example_file" ]; then
            echo "Creating $config_file from example..."
            cp "$example_file" "$config_file"

            # Generate random secrets
            echo "Generating secure secrets for $config_file..."
            jwt_secret=$(python3 -c "import secrets; print(secrets.token_hex(32))")
            password=$(python3 -c "import secrets; print(secrets.token_urlsafe(16))")

            # Inject secrets using jq
            tmp=$(mktemp)
            jq --arg jwt "$jwt_secret" --arg pwd "$password" \
               '.api_server.jwt_secret_key = $jwt | .api_server.password = $pwd' \
               "$config_file" > "$tmp" && mv "$tmp" "$config_file"

            echo "Secrets injected into $config_file."
        else
            echo "WARNING: Example config $example_file not found!"
        fi
    else
        echo "$config_file already exists."
    fi
}

setup_config "user_data/configs/config.delta.dryrun.json"
setup_config "user_data/configs/config.delta.live.json"

echo "Bootstrap complete."
echo "Next steps:"
echo "1. Edit .env with your API credentials."
echo "2. Run 'scripts/validate_exchange.sh' to verify connectivity and markets."
echo "3. Run 'scripts/run_dryrun.sh' to start the bot in dry-run mode."
