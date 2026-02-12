#!/bin/bash
set -e

# Ensure we are in the root
cd "$(dirname "$0")/.."

DELTA_ENV=${DELTA_ENV:-india_testnet}
TIMESTAMP=$(date -u +"%Y%m%d_%H%M%S")
REPORTS_DIR="user_data/reports"
PAIRLISTS_DIR="user_data/pairlists"
MARKETS_FILE="$REPORTS_DIR/markets_${TIMESTAMP}.json"

# Ensure dirs exist
mkdir -p "$REPORTS_DIR"
mkdir -p "$PAIRLISTS_DIR"

echo "Fetching markets for $DELTA_ENV..."

# Find latest previous dump for drift check
PREV_DUMP=$(ls -t "$REPORTS_DIR"/markets_*.json 2>/dev/null | head -n 1 || echo "")

# Fetch Markets using custom tool inside Docker
# We capture stdout to the file.
# Note: we must ensure no other output goes to stdout (logging to stderr).
docker compose run --rm -e DELTA_ENV="$DELTA_ENV" freqtrade \
    python3 /freqtrade/custom_tools/fetch_markets.py > "$MARKETS_FILE"

if [ ! -s "$MARKETS_FILE" ]; then
    echo "Error: Markets file is empty."
    rm "$MARKETS_FILE"
    exit 1
fi

echo "Markets saved to $MARKETS_FILE"

# Validate Schema & Drift
echo "Validating schema..."
# We map the reports dir so the container can see the previous file
# The container path for reports is /freqtrade/user_data/reports
# So we need to translate host path to container path for arguments
CONTAINER_MARKETS_FILE="/freqtrade/user_data/reports/markets_${TIMESTAMP}.json"
if [ -n "$PREV_DUMP" ]; then
    CONTAINER_PREV_DUMP="/freqtrade/user_data/reports/$(basename "$PREV_DUMP")"
else
    CONTAINER_PREV_DUMP=""
fi

docker compose run --rm \
    -e MIN_MARKETS="${MIN_MARKETS:-20}" \
    -e MAX_REMOVAL_RATIO="${MAX_REMOVAL_RATIO:-0.25}" \
    -e STRICT_VOLUME="${STRICT_VOLUME:-false}" \
    freqtrade \
    python3 /freqtrade/custom_tools/validate_markets_schema.py "$CONTAINER_MARKETS_FILE" "$CONTAINER_PREV_DUMP"

if [ $? -ne 0 ]; then
    echo "Validation Failed! Keeping dump for inspection but aborting update."
    # We might want to rename it to failed
    mv "$MARKETS_FILE" "${MARKETS_FILE%.json}_failed.json"
    exit 1
fi

# Generate Whitelist
echo "Generating whitelist..."
WHITELIST_JSON="$PAIRLISTS_DIR/whitelist.delta.json"
WHITELIST_TXT="$PAIRLISTS_DIR/whitelist.delta.txt"

# Run generator inside docker
docker compose run --rm \
    -e FILTER_MODE="${FILTER_MODE:-perps_usdt}" \
    -e ALLOWLIST_REGEX="${ALLOWLIST_REGEX:-.*}" \
    freqtrade \
    python3 /freqtrade/custom_tools/generate_whitelist.py "$CONTAINER_MARKETS_FILE" > "$WHITELIST_JSON"

# Generate simple TXT list
grep -o '"[^"]*:[^"]*"' "$WHITELIST_JSON" | tr -d '"' > "$WHITELIST_TXT"

echo "Whitelist updated at $WHITELIST_JSON"

# Generate Drift Report (Diff)
DIFF_FILE="$REPORTS_DIR/whitelist_diff_${TIMESTAMP}.md"
echo "# Whitelist Drift Report" > "$DIFF_FILE"
echo "Date: $TIMESTAMP" >> "$DIFF_FILE"
echo "Env: $DELTA_ENV" >> "$DIFF_FILE"
echo "Previous Dump: $(basename "$PREV_DUMP")" >> "$DIFF_FILE"
echo "Current Dump: $(basename "$MARKETS_FILE")" >> "$DIFF_FILE"
echo "" >> "$DIFF_FILE"

if [ -n "$PREV_DUMP" ]; then
    echo "## Stats" >> "$DIFF_FILE"
    COUNT=$(grep -c ":" "$WHITELIST_TXT")
    echo "Total Pairs: $COUNT" >> "$DIFF_FILE"
fi

# Cleanup old dumps (keep last 7)
echo "Cleaning up old dumps..."
ls -t "$REPORTS_DIR"/markets_*.json | tail -n +8 | xargs -I {} rm -- {} 2>/dev/null || true

echo "Done."
