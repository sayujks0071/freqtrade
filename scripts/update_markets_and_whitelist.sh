#!/bin/bash
set -e

# Source common env and functions
source "$(dirname "$0")/common.sh"

echo "Updating Markets and Whitelist for $DELTA_ENV..."

# 1. Fetch Markets
REPORT_FILE="user_data/reports/markets_$(date +%Y%m%d_%H%M%S).json"
LATEST_LINK="user_data/reports/markets_latest.json"

echo "Fetching markets to $REPORT_FILE..."

# We run list-markets inside the container
docker compose run --rm \
    -e FREQTRADE__EXCHANGE__CCXT_CONFIG__URLS__API__public="$FREQTRADE__EXCHANGE__CCXT_CONFIG__URLS__API__public" \
    -e FREQTRADE__EXCHANGE__CCXT_CONFIG__URLS__API__private="$FREQTRADE__EXCHANGE__CCXT_CONFIG__URLS__API__private" \
    freqtrade list-markets \
    --exchange delta \
    --trading-mode futures \
    --print-json > "$REPORT_FILE"

# Check if file is valid
if [ ! -s "$REPORT_FILE" ]; then
    echo "Error: Market dump is empty."
    exit 1
fi

ln -sf "$(basename "$REPORT_FILE")" "$LATEST_LINK"

# 2. Generate Whitelist
WHITELIST_FILE="user_data/pairlists/whitelist.delta.json"
echo "Generating whitelist from markets..."

# Use the python tool to filter markets and generate whitelist
# We map ./tools to /freqtrade/tools
# We assume the tool prints JSON to stdout
docker compose run --rm --entrypoint python3 \
    freqtrade \
    /freqtrade/tools/generate_whitelist.py "/freqtrade/$REPORT_FILE" > "$WHITELIST_FILE"

if [ -s "$WHITELIST_FILE" ]; then
    echo "Whitelist updated at $WHITELIST_FILE"
    echo "Top 5 pairs:"
    grep -A 5 "pair_whitelist" "$WHITELIST_FILE"
else
    echo "Error: Failed to generate whitelist."
    exit 1
fi

echo "Update Complete."
