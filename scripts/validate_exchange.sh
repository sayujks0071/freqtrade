#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Source common functions if available
if [ -f "$DIR/common.sh" ]; then
    source "$DIR/common.sh"
fi

echo "Validating Exchange Connection and Markets..."

# Ensure we are in the root
cd "$(dirname "$0")/.."

# Run the update script which handles fetching, validation, and whitelist generation
./scripts/update_markets_and_whitelist.sh

if [ $? -eq 0 ]; then
    echo "Validation Successful."
else
    echo "Validation Failed."
    exit 1
fi
