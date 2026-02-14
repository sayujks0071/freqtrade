#!/bin/bash
set -e

# Change to repo root
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR/.."

source "$DIR/common.sh"

TIMESTAMP=$(date -u +"%Y%m%d_%H%M%S")
REPORTS_DIR="user_data/reports"
PAIRLISTS_DIR="user_data/pairlists"
MARKETS_FILE="$REPORTS_DIR/markets_${TIMESTAMP}.json"

mkdir -p $REPORTS_DIR
mkdir -p $PAIRLISTS_DIR

# Find latest previous dump
PREV_DUMP=$(ls -t $REPORTS_DIR/markets_*.json 2>/dev/null | head -n 1 || echo "")

echo "Fetching markets from Delta ($DELTA_ENV)..."

# Run freqtrade list-markets via Docker
# We map the output to a file.
TEMP_OUTPUT=$(mktemp)

# Use dryrun config for connection settings
CONFIG_FILE="/freqtrade/user_data/configs/config.delta.dryrun.json"

docker compose run --rm freqtrade list-markets \
    --config "$CONFIG_FILE" \
    --exchange delta \
    --trading-mode futures \
    --print-json > "$TEMP_OUTPUT"

# Extract JSON array (lines starting with [)
grep -o '\[.*\]' "$TEMP_OUTPUT" > "$MARKETS_FILE" || true

rm "$TEMP_OUTPUT"

if [ ! -s "$MARKETS_FILE" ]; then
    echo "Error: Failed to fetch markets or parse output."
    exit 1
fi

echo "Saved markets to $MARKETS_FILE"

echo "Validating schema and whitelist..."

# Construct arguments for validator
ARGS="--markets $MARKETS_FILE --env $DELTA_ENV"

# Use python to run the tools (assuming python3 is available on host as per other scripts)
# Or we could run inside docker, but we are managing files on host.
# We assume python3 with minimal dependencies (json) or use the venv if available?
# The tools import modules from the repo?
# tools/validate_markets_schema.py seems to depend on things.
# Let's assume the host has python3 environment or we should run this inside docker?
# The prompt implies we have "tools/" which are likely python scripts.
# running inside docker is safer for dependencies.
# But "tools/generate_whitelist.py" outputs to stdout which we redirect.

# Let's run on host for now, assuming standard python.
# If they fail, we might need to use `docker compose run --rm freqtrade python3 ...`
# But mounting `tools` is not default in docker-compose.yml (only user_data).
# So we must rely on host python or mount tools.

# Given the instructions "Deliverables ... scripts/", we usually assume host scripts.

python3 tools/validate_markets_schema.py $ARGS

echo "Generating whitelist..."
WHITELIST_JSON="$PAIRLISTS_DIR/whitelist.delta.json"

# Generate whitelist
python3 tools/generate_whitelist.py --input "$MARKETS_FILE" --filter-mode "${FILTER_MODE:-perps_usdt}" > "$WHITELIST_JSON"

echo "Whitelist updated at $WHITELIST_JSON"

# Clean up old dumps (keep last 7)
ls -t $REPORTS_DIR/markets_*.json | tail -n +8 | xargs -I {} rm -- {} 2>/dev/null || true

echo "Done."
