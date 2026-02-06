#!/bin/bash
set -e

# Ensure root
cd "$(dirname "$0")/.."

DELTA_ENV=${DELTA_ENV:-india_testnet}
TIMESTAMP=$(date -u +"%Y%m%d_%H%M%S")
REPORTS_DIR="user_data/reports"
PAIRLISTS_DIR="user_data/pairlists"
MARKETS_FILE="$REPORTS_DIR/markets_${TIMESTAMP}.json"

mkdir -p $REPORTS_DIR
mkdir -p $PAIRLISTS_DIR

# Find latest previous dump
PREV_DUMP=$(ls -t $REPORTS_DIR/markets_*.json 2>/dev/null | head -n 1 || echo "")

echo "Fetching markets for $DELTA_ENV..."

# Run freqtrade list-markets via Docker
# We map the output to a file.
# Note: Ensure .env is loaded or vars passed
if [ -f .env ]; then
    export $(cat .env | xargs)
fi

# We use a temporary file for the docker output because of potential log noise
TEMP_OUTPUT=$(mktemp)

# Command to fetch markets.
# We explicitly set config to delta dryrun (or any config with exchange delta)
# or just pass args.
# We need to ensure we connect to the right exchange environment.
# Since config.delta.dryrun.json has exchange settings, we use it.
# But we need to make sure 'list-markets' uses the config credentials/urls.

docker compose run --rm freqtrade list-markets \
    --config /freqtrade/user_data/configs/config.delta.dryrun.json \
    --print-json > $TEMP_OUTPUT

# Check if successful
if [ $? -ne 0 ]; then
    echo "Failed to fetch markets"
    rm $TEMP_OUTPUT
    exit 1
fi

# Move temp output to final location, filtering if necessary (sometimes logs get mixed)
# Assuming freqtrade outputs pure JSON on stdout when --print-json is used,
# but sometimes connection logs appear.
# We can try to extract JSON.
# Python oneliner to extract json from potentially noisy output?
# Or we assume freqtrade is quiet.
# Let's try to just copy it for now, and the validator will fail if it's not valid JSON.

mv $TEMP_OUTPUT $MARKETS_FILE

WHITELIST_JSON="$PAIRLISTS_DIR/whitelist.delta.json"
REPORT_FILE="$REPORTS_DIR/markets_schema_report_${TIMESTAMP}.md"

echo "Validating schema..."
python3 tools/validate_markets_schema.py \
    --markets "$MARKETS_FILE" \
    --env "$DELTA_ENV" \
    --prev-whitelist "$WHITELIST_JSON" \
    --out-report "$REPORT_FILE"

# If validation failed, the script would have exited due to set -e (exit code 2)
# If we are here, validation passed.

echo "Generating whitelist..."
WHITELIST_TXT="$PAIRLISTS_DIR/whitelist.delta.txt"

python3 tools/generate_whitelist.py "$MARKETS_FILE" > "$WHITELIST_JSON"

# Also generate TXT list (symbols only)
grep -o '"[^"]*:[^"]*"' "$WHITELIST_JSON" | tr -d '"' > "$WHITELIST_TXT"

echo "Whitelist updated at $WHITELIST_JSON"

# Drift Report (Diff)
if [ -n "$PREV_DUMP" ]; then
    DIFF_FILE="$REPORTS_DIR/whitelist_diff_${TIMESTAMP}.md"
    echo "# Whitelist Drift Report" > $DIFF_FILE
    echo "Date: $TIMESTAMP" >> $DIFF_FILE
    echo "Previous: $PREV_DUMP" >> $DIFF_FILE
    echo "Current: $MARKETS_FILE" >> $DIFF_FILE
    echo "" >> $DIFF_FILE
    echo "## Changes" >> $DIFF_FILE
    # Simple diff of symbols could be done here or via python
    # For now, just a placeholder or simple diff command
    # diff <(grep ... prev) <(grep ... curr)
    echo "Generated via update script." >> $DIFF_FILE
fi

# Clean up old dumps (keep last 7)
ls -t $REPORTS_DIR/markets_*.json | tail -n +8 | xargs -I {} rm -- {} 2>/dev/null || true

echo "Done."
