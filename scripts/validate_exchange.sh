#!/bin/bash
set -e

echo "Validating exchange connection and markets..."
DATE=$(date -u +"%Y-%m-%d_%H%M%S")
MARKETS_FILE="user_data/reports/markets_check_${DATE}.json"

python3 tools/fetch_markets.py --exchange delta --output "$MARKETS_FILE" --env "${DELTA_ENV:-india_prod}"

echo "Validating schema..."
python3 tools/validate_markets_schema.py --markets "$MARKETS_FILE" --out-report "user_data/reports/validation_check_${DATE}.md"

echo "Validation successful."
