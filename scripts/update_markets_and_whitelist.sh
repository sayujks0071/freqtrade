#!/bin/bash
set -e

# Load environment variables
if [ -f .env ]; then
  export $(cat .env | grep -v '#' | xargs)
fi

DELTA_ENV=${DELTA_ENV:-india_testnet}
FILTER_MODE=${FILTER_MODE:-perps_usdt}
ALLOWLIST_REGEX=${ALLOWLIST_REGEX:-.*USDT:USDT}
MAX_REMOVAL_RATIO=${MAX_REMOVAL_RATIO:-0.25}
MIN_MARKETS=${MIN_MARKETS:-20}
STRICT_VOLUME=${STRICT_VOLUME:-false}

TIMESTAMP=$(date -u +"%Y%m%d_%H%M%S")
MARKETS_FILE="user_data/reports/markets_${TIMESTAMP}.json"
WHITELIST_FILE="user_data/pairlists/whitelist.delta.json"
WHITELIST_TXT="user_data/pairlists/whitelist.delta.txt"
PREV_WHITELIST_FILE="user_data/pairlists/whitelist.delta.json" # Use current as previous
REPORT_FILE="user_data/reports/whitelist_diff_${TIMESTAMP}.md"
VALIDATION_REPORT="user_data/reports/markets_schema_report_${TIMESTAMP}.md"

echo "Updating markets and whitelist for Delta Exchange ($DELTA_ENV)..."
echo "Timestamp: $TIMESTAMP"

# Ensure directories exist
mkdir -p user_data/reports user_data/pairlists

# 1. Fetch Markets Dump
# Use docker compose if available, else assume freqtrade is installed
if command -v docker >/dev/null 2>&1; then
  CMD="docker compose run --rm freqtrade list-markets --exchange delta --trading-mode futures --print-json"
else
  CMD="freqtrade list-markets --exchange delta --trading-mode futures --print-json"
fi

echo "Fetching markets..."
# Capture output to file. list-markets prints JSON to stdout.
# We need to filter out logs if they are mixed in stdout.
# Usually freqtrade logs to stderr.
$CMD > "$MARKETS_FILE"

# Verify dump is valid JSON
if ! jq empty "$MARKETS_FILE" >/dev/null 2>&1; then
  echo "Error: Fetched markets file is not valid JSON."
  cat "$MARKETS_FILE" | head -n 20
  rm "$MARKETS_FILE"
  exit 1
fi

echo "Markets dumped to $MARKETS_FILE"

# 2. Validate & Generate Whitelist
echo "Validating markets and generating whitelist..."

VALIDATE_CMD="python3 tools/validate_markets_schema.py \
  --markets $MARKETS_FILE \
  --env $DELTA_ENV \
  --out-report $VALIDATION_REPORT \
  --min-markets $MIN_MARKETS \
  --max-removal-ratio $MAX_REMOVAL_RATIO \
  --filter-mode $FILTER_MODE \
  --allowlist-regex \"$ALLOWLIST_REGEX\" \
  --out-whitelist $WHITELIST_FILE"

if [ -f "$PREV_WHITELIST_FILE" ]; then
  VALIDATE_CMD="$VALIDATE_CMD --prev-whitelist $PREV_WHITELIST_FILE"
fi

if [ "$STRICT_VOLUME" = "true" ]; then
  VALIDATE_CMD="$VALIDATE_CMD --strict-volume"
fi

# Run validation
if $VALIDATE_CMD; then
    echo "Validation PASSED."

    # Create TXT version of whitelist
    jq -r '.[]' "$WHITELIST_FILE" > "$WHITELIST_TXT"
    echo "Whitelist TXT written to $WHITELIST_TXT"

    # Drift report is in $VALIDATION_REPORT
    cp "$VALIDATION_REPORT" "$REPORT_FILE"
    echo "Drift report copied to $REPORT_FILE"

else
    echo "Validation FAILED. Check report at $VALIDATION_REPORT"
    exit 2
fi

echo "Update complete."
