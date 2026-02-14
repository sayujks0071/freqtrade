#!/bin/bash
set -e
cd "$(dirname "$0")/.."

# Source environment
source scripts/common.sh

# Defaults
DELTA_ENV=${DELTA_ENV:-india_testnet}
FILTER_MODE=${FILTER_MODE:-perps_usdt}
MIN_MARKETS=${MIN_MARKETS:-20}
MAX_REMOVAL_RATIO=${MAX_REMOVAL_RATIO:-0.25}

echo "Updating markets and whitelist for $DELTA_ENV (Filter: $FILTER_MODE)..."

TIMESTAMP=$(date -u +%Y%m%d_%H%M%S)
MARKETS_FILE="user_data/reports/markets_${DELTA_ENV}_${TIMESTAMP}.json"
REPORT_FILE="user_data/reports/markets_schema_report_${DELTA_ENV}_${TIMESTAMP}.md"
CURRENT_WHITELIST="user_data/pairlists/whitelist.delta.${DELTA_ENV}.json"
CANDIDATE_WHITELIST="user_data/pairlists/whitelist.delta.${DELTA_ENV}.candidate.json"
TXT_WHITELIST="user_data/pairlists/whitelist.delta.${DELTA_ENV}.txt"

# Ensure directories
mkdir -p user_data/reports user_data/pairlists

# 1. Fetch Markets
echo "Fetching markets..."
# Redirect logs to stderr or file to keep stdout clean (though we write to file directly)
docker compose run --rm freqtrade list-markets \
    --exchange delta \
    --trading-mode futures \
    --print-json \
    --logfile /freqtrade/user_data/logs/list_markets_update.log > "$MARKETS_FILE"

if [ ! -s "$MARKETS_FILE" ]; then
    echo "ERROR: Failed to fetch markets."
    exit 1
fi

# 2. Validate & Generate Candidate Whitelist
echo "Validating markets and generating whitelist..."
# Python script needs environment variables
export MIN_MARKETS
export MAX_REMOVAL_RATIO
export FILTER_MODE
export ALLOWLIST_REGEX

# Check if current whitelist exists for drift check
PREV_ARG=""
if [ -f "$CURRENT_WHITELIST" ]; then
    PREV_ARG="--prev-whitelist $CURRENT_WHITELIST"
fi

set +e # Allow python script to fail with exit code
python3 tools/validate_markets_schema.py \
    --markets "$MARKETS_FILE" \
    --candidate-whitelist "$CANDIDATE_WHITELIST" \
    $PREV_ARG \
    --env "$DELTA_ENV" \
    --out-report "$REPORT_FILE"

EXIT_CODE=$?
set -e

if [ $EXIT_CODE -eq 0 ]; then
    echo "Validation PASSED."

    # Atomic update
    mv "$CANDIDATE_WHITELIST" "$CURRENT_WHITELIST"

    # Generate TXT version
    # Extract pairs from json using jq or python
    python3 -c "import json; print('\n'.join(json.load(open('$CURRENT_WHITELIST'))['exchange']['pair_whitelist']))" > "$TXT_WHITELIST"

    echo "Updated whitelist: $CURRENT_WHITELIST"
    echo "Updated text whitelist: $TXT_WHITELIST"

else
    echo "Validation FAILED (Exit Code: $EXIT_CODE). Check report: $REPORT_FILE"
    # Move failed dump to failed folder or rename?
    mv "$MARKETS_FILE" "user_data/reports/markets_failed_${TIMESTAMP}.json"
    exit 1
fi

# 3. Cleanup / Rotate
# Keep last 7 market dumps
echo "Cleaning up old dumps..."
ls -t user_data/reports/markets_${DELTA_ENV}_*.json | tail -n +8 | xargs -r rm --

echo "Done."
