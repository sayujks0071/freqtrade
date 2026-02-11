#!/bin/bash
set -e

# Load .env variables
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Defaults
DELTA_ENV=${DELTA_ENV:-india_prod}
FILTER_MODE=${FILTER_MODE:-perps_usdt}
TIMESTAMP=$(date -u +"%Y%m%d_%H%M%S")
REPORTS_DIR="user_data/reports"

mkdir -p "$REPORTS_DIR"

echo "Running Market Refresh for ENV: $DELTA_ENV (Filter: $FILTER_MODE)"

# 1. Fetch Markets
# We use docker run to ensure we use the same ccxt version/env as the bot
# But running docker inside a script might be tricky if we are already in docker (not the case usually for CI or host scripts)
# Assuming this runs on host where docker is available.
# Or if run inside docker, we just call freqtrade directly.

MARKETS_FILE="$REPORTS_DIR/markets_schema_report_${TIMESTAMP}.json"

# Check if we are inside docker container
if [ -f /.dockerenv ]; then
    CMD="freqtrade"
else
    CMD="docker compose run --rm freqtrade"
fi

echo "Fetching markets..."
$CMD list-markets \
    --exchange delta \
    --trading-mode futures \
    --print-json \
    > "$MARKETS_FILE" 2>/dev/null

if [ ! -s "$MARKETS_FILE" ]; then
    echo "FAIL: Market dump empty or failed."
    rm -f "$MARKETS_FILE"
    exit 1
fi

# 2. Find Previous Dump for Drift Check
# Sort by name (timestamp) and take the last one before current
PREV_DUMP=$(ls -1 "$REPORTS_DIR"/markets_schema_report_*.json 2>/dev/null | grep -v "$TIMESTAMP" | sort | tail -n 1)

if [ -n "$PREV_DUMP" ]; then
    echo "Previous dump found: $PREV_DUMP"
else
    echo "No previous dump found for drift check."
fi

# 3. Validate Schema & Drift
echo "Validating schema..."
# We run python script locally
if ! python3 tools/validate_markets_schema.py "$MARKETS_FILE" "$PREV_DUMP"; then
    echo "FAIL: Schema validation failed."
    # We might want to keep the bad file for debugging, but fail the script
    exit 1
fi

# 4. Generate Whitelist
echo "Generating whitelist..."
# Set env var for generate_whitelist
export FILTER_MODE
export DELTA_ENV
python3 tools/generate_whitelist.py "$MARKETS_FILE"

# 5. Cleanup / Rotate
# Keep last 7 json dumps
echo "Cleaning up old dumps..."
ls -1t "$REPORTS_DIR"/markets_schema_report_*.json | tail -n +8 | xargs -I {} rm -- {} 2>/dev/null || true
# Keep last 7 reports (md)
ls -1t "$REPORTS_DIR"/markets_schema_report_*.md | tail -n +8 | xargs -I {} rm -- {} 2>/dev/null || true

echo "Market refresh complete."
