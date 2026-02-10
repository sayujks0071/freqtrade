#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$DIR/common.sh"

echo "Validating Delta Exchange Connectivity ($DELTA_ENV)..."

# 1. Verify 'delta' exchange is available
echo "Checking if 'delta' exchange is supported..."
# We capture output to check for 'delta'
# --one-column lists exchanges one per line
SUPPORTED=$(docker compose run --rm freqtrade list-exchanges --one-column | grep "^delta$")
if [ "$SUPPORTED" != "delta" ]; then
    echo "ERROR: Exchange 'delta' not found in freqtrade supported exchanges!"
    exit 1
fi
echo "Exchange 'delta' is supported."

# 2. Fetch markets
TIMESTAMP=$(date -u +"%Y%m%d_%H%M%S")
REPORT_FILE="user_data/reports/markets_${TIMESTAMP}.json"
echo "Fetching markets to $REPORT_FILE..."

# Ensure log directory exists
mkdir -p user_data/logs

# Run list-markets
# We redirect logs to a file to keep stdout clean for JSON output
# We pass the config to ensure API keys/URLs are loaded (via env vars or config)
docker compose run --rm freqtrade list-markets \
    --logfile /freqtrade/user_data/logs/validate.log \
    --config /freqtrade/user_data/configs/config.delta.dryrun.json \
    --exchange delta \
    --trading-mode futures \
    --print-json > "${REPORT_FILE}.tmp"

# Check if file exists and has content
if [ ! -s "${REPORT_FILE}.tmp" ]; then
    echo "ERROR: Failed to fetch markets (empty output)."
    rm -f "${REPORT_FILE}.tmp"
    exit 1
fi

# Attempt to locate JSON start (in case of stray stdout logs)
# We assume JSON starts with [ or {
# Using sed to extract from the first occurrence of [ or { to the end
sed -n '/^[\[{]/,$p' "${REPORT_FILE}.tmp" > "$REPORT_FILE"

if [ ! -s "$REPORT_FILE" ]; then
    echo "ERROR: No JSON found in output."
    echo "Raw output:"
    cat "${REPORT_FILE}.tmp"
    rm -f "${REPORT_FILE}.tmp" "$REPORT_FILE"
    exit 1
fi
rm "${REPORT_FILE}.tmp"

echo "Markets fetched successfully."

# 3. Validate Schema
echo "Validating market schema..."
# Assuming tools/validate_markets_schema.py is available
if [ -f "tools/validate_markets_schema.py" ]; then
    python3 tools/validate_markets_schema.py "$REPORT_FILE"
else
    echo "WARNING: tools/validate_markets_schema.py not found. Skipping schema validation."
fi

# 4. Generate Whitelist
echo "Generating whitelist..."
WHITELIST_FILE="user_data/pairlists/whitelist.delta.json"
if [ -f "tools/generate_whitelist.py" ]; then
    python3 tools/generate_whitelist.py "$REPORT_FILE" > "$WHITELIST_FILE"

    if [ ! -s "$WHITELIST_FILE" ]; then
        echo "ERROR: Failed to generate whitelist."
        exit 1
    fi
    echo "Whitelist generated at $WHITELIST_FILE"
else
    echo "ERROR: tools/generate_whitelist.py not found!"
    exit 1
fi

echo "Validation Complete. System is ready for dry-run."
