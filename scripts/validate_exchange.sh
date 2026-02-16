#!/bin/bash
set -e

# Load env
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

echo "Validating Delta Exchange connection..."

# Command check
if command -v freqtrade &> /dev/null; then
    CMD="freqtrade"
elif command -v docker &> /dev/null; then
    CMD="docker compose run --rm freqtrade"
else
    echo "Error: Freqtrade or Docker not found."
    exit 1
fi

echo "Using: $CMD"

# 1. Fetch Markets (dry-run check)
echo "Fetching markets..."
mkdir -p user_data/reports
MARKETS_JSON="user_data/reports/markets_check.json"

# Check if we can run list-markets
if ! $CMD list-markets --config user_data/configs/config.delta.dryrun.json --print-json > "$MARKETS_JSON"; then
    echo "Error: 'list-markets' command failed."
    exit 1
fi

if [ ! -s "$MARKETS_JSON" ]; then
    echo "Error: Failed to fetch markets or empty response."
    rm "$MARKETS_JSON"
    exit 1
fi

MARKET_COUNT=$(grep -o '"symbol":' "$MARKETS_JSON" | wc -l)
echo "Found $MARKET_COUNT markets."

if [ "$MARKET_COUNT" -lt 10 ]; then
    echo "Warning: Very few markets found (<10). Check API connection or URL."
fi

# 2. Check Whitelist
WHITELIST="user_data/pairlists/whitelist.delta.json"
if [ -f "$WHITELIST" ]; then
    PAIRS_COUNT=$(grep -o '"[A-Z0-9]\+/[A-Z0-9]\+:[A-Z0-9]\+"' "$WHITELIST" | wc -l)
    echo "Whitelist contains $PAIRS_COUNT pairs."
else
    echo "Warning: Whitelist file not found ($WHITELIST). Run ./scripts/update_markets_and_whitelist.sh first."
fi

rm "$MARKETS_JSON"
echo "Validation Successful."
