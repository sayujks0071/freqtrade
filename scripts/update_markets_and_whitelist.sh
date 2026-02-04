#!/bin/bash
set -e

# Load env
if [ -f .env ]; then
    export $(cat .env | grep -v '#' | xargs)
fi

DELTA_ENV=${DELTA_ENV:-india_prod}
FILTER_MODE=${FILTER_MODE:-perps_usdt}
MIN_MARKETS=${MIN_MARKETS:-20}
MAX_REMOVAL_RATIO=${MAX_REMOVAL_RATIO:-0.25}
STRICT_VOLUME=${STRICT_VOLUME:-false}

DATE=$(date -u +"%Y-%m-%d")
MARKETS_FILE="user_data/reports/markets_${DATE}.json"
WHITELIST_FILE="user_data/pairlists/whitelist.delta.json"
WHITELIST_TXT="user_data/pairlists/whitelist.delta.txt"
# If whitelist exists, use it as previous for drift check
if [ -f "$WHITELIST_FILE" ]; then
    PREV_WHITELIST_FILE="$WHITELIST_FILE"
else
    PREV_WHITELIST_FILE=""
fi
REPORT_FILE="user_data/reports/markets_schema_report_${DATE}.md"

echo "Updating markets for $DELTA_ENV with filter $FILTER_MODE..."

# Fetch
python3 tools/fetch_markets.py --exchange delta --output "$MARKETS_FILE" --env "$DELTA_ENV"

# Validate
echo "Validating markets..."
if [ "$STRICT_VOLUME" = "true" ]; then
    STRICT_FLAG="--strict-volume"
else
    STRICT_FLAG=""
fi

if [ -n "$PREV_WHITELIST_FILE" ]; then
    PREV_FLAG="--prev-whitelist $PREV_WHITELIST_FILE"
else
    PREV_FLAG=""
fi

python3 tools/validate_markets_schema.py \
    --markets "$MARKETS_FILE" \
    --min-markets "$MIN_MARKETS" \
    --max-removal-ratio "$MAX_REMOVAL_RATIO" \
    $PREV_FLAG \
    --out-report "$REPORT_FILE" \
    --env "$DELTA_ENV" \
    $STRICT_FLAG

echo "Validation passed. Generating whitelist..."

# Generate Whitelist
python3 tools/generate_whitelist.py \
    --markets "$MARKETS_FILE" \
    --filter-mode "$FILTER_MODE" \
    --allowlist-regex "${ALLOWLIST_REGEX:-.*}" \
    --output "$WHITELIST_FILE" \
    --output-txt "$WHITELIST_TXT"

echo "Whitelist generated at $WHITELIST_FILE"
