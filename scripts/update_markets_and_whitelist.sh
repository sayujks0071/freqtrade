#!/bin/bash
set -e

# Ensure root
cd "$(dirname "$0")/.."

DELTA_ENV=${DELTA_ENV:-india_testnet}
TIMESTAMP=$(date -u +"%Y%m%d_%H%M%S")
REPORTS_DIR="user_data/reports"
PAIRLISTS_DIR="user_data/pairlists"

mkdir -p $REPORTS_DIR
mkdir -p $PAIRLISTS_DIR

# Paths
EXISTING_WHITELIST="$PAIRLISTS_DIR/whitelist.delta.json"
FINAL_MARKETS_FILE="$REPORTS_DIR/markets_${TIMESTAMP}.json"
REPORT_FILE="$REPORTS_DIR/markets_schema_report_${TIMESTAMP}.md"
FAILED_MARKETS_FILE="$REPORTS_DIR/markets_failed_${TIMESTAMP}.json"

echo "Fetching markets for $DELTA_ENV..."

# Load env if exists
if [ -f .env ]; then
    export $(cat .env | xargs)
fi

# Temporary files
TEMP_MARKETS=$(mktemp)
TEMP_WHITELIST=$(mktemp)

# 1. Fetch Markets
# We capture output to temp file. Freqtrade might output logs to stderr, JSON to stdout.
# We redirect stderr to null or a log file to keep JSON clean?
# Better to redirect stderr to >&2 (default) and stdout to file.
# But freqtrade docker might mix them if tty is allocated.
# --rm implies no tty if not interactive?
# We use `docker compose run --rm -T` to disable TTY to avoid control characters.

docker compose run --rm -T freqtrade list-markets \
    --config /freqtrade/user_data/configs/config.delta.dryrun.json \
    --print-json > $TEMP_MARKETS

if [ $? -ne 0 ]; then
    echo "Failed to fetch markets"
    rm $TEMP_MARKETS $TEMP_WHITELIST
    exit 1
fi

# Check if TEMP_MARKETS is valid JSON or empty
if [ ! -s $TEMP_MARKETS ]; then
    echo "Fetched markets file is empty!"
    rm $TEMP_MARKETS $TEMP_WHITELIST
    exit 1
fi

# 2. Generate Candidate Whitelist
echo "Generating candidate whitelist..."
python3 tools/generate_whitelist.py "$TEMP_MARKETS" > "$TEMP_WHITELIST"

if [ $? -ne 0 ]; then
    echo "Failed to generate whitelist"
    rm $TEMP_MARKETS $TEMP_WHITELIST
    exit 1
fi

# 3. Validate Schema & Drift
echo "Validating schema and drift..."
set +e # Disable exit on error to handle validation failure manually
python3 tools/validate_markets_schema.py \
    --markets "$TEMP_MARKETS" \
    --candidate-whitelist "$TEMP_WHITELIST" \
    --prev-whitelist "$EXISTING_WHITELIST" \
    --env "$DELTA_ENV" \
    --out-report "$REPORT_FILE"

VALIDATION_EXIT_CODE=$?
set -e # Re-enable exit on error

if [ $VALIDATION_EXIT_CODE -eq 0 ]; then
    echo "Validation PASS."

    # 4. Success: Move files
    mv $TEMP_MARKETS $FINAL_MARKETS_FILE
    mv $TEMP_WHITELIST $EXISTING_WHITELIST

    # Generate TXT list
    WHITELIST_TXT="$PAIRLISTS_DIR/whitelist.delta.txt"
    grep -o '"[^"]*:[^"]*"' "$EXISTING_WHITELIST" | tr -d '"' > "$WHITELIST_TXT"

    echo "Whitelist updated at $EXISTING_WHITELIST"
    echo "Report written to $REPORT_FILE"

    # Clean up old reports (keep last 7)
    ls -t $REPORTS_DIR/markets_schema_report_*.md 2>/dev/null | tail -n +8 | xargs -I {} rm -- {} 2>/dev/null || true
    ls -t $REPORTS_DIR/markets_*.json 2>/dev/null | tail -n +8 | xargs -I {} rm -- {} 2>/dev/null || true

else
    echo "Validation FAILED (Exit Code: $VALIDATION_EXIT_CODE)."

    # 5. Failure: Save failed markets for debugging
    mv $TEMP_MARKETS $FAILED_MARKETS_FILE
    rm $TEMP_WHITELIST

    echo "Failed markets dump saved to $FAILED_MARKETS_FILE"
    echo "See report at $REPORT_FILE"

    # Fail the script
    exit 1
fi

echo "Done."
