#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$DIR/common.sh"

export FREQTRADE_CONFIG_FILE="config.delta.dryrun.json"

echo "Starting Freqtrade in DRY-RUN mode ($DELTA_ENV)..."

# Pre-flight check
if [ ! -f "user_data/pairlists/whitelist.delta.json" ]; then
    echo "WARNING: Whitelist file not found!"
    echo "Please run 'scripts/validate_exchange.sh' first to generate it."
    # Non-interactive fallback if no TTY
    if [ -t 0 ]; then
        read -p "Do you want to run validation now? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            ./scripts/validate_exchange.sh
            if [ $? -ne 0 ]; then
                 echo "Validation failed. Aborting start."
                 exit 1
            fi
        fi
    else
        echo "Skipping validation prompt (non-interactive)."
    fi
fi

docker compose up -d

echo "Container started."
echo "View logs: docker compose logs -f"
