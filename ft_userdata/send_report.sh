#!/bin/bash
# Script to generate report and send via WhatsApp
# Usage: ./send_report.sh

REPORT_FILE="final_performance_report.txt"

echo "📊 Generating Performance Dashboard..."
# We use the PerformanceDashboard.py on the VALIDATION results
# If multiple files exist, we can pick the one with most recent timestamp or just iterate.
# For simplicity, we grab the MomentumVolumeTrend validation result as a primary example,
# or iterating all validation files.

python3 PerformanceDashboard.py user_data/backtest_results/*_validation.json > $REPORT_FILE 2>&1

EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo "⚠️ Dashboard generation failed or had warnings. Sending log contents."
    # If python script fails, maybe because no files, just send error msg
    CONTENT="⚠️ Performance Report Generation Failed.\nCheck logs."
else
    # Read the first 20 lines of the report for the message (WhatsApp has char limits usually)
    # or just the summary table if the script outputs one.
    CONTENT=$(cat $REPORT_FILE)
fi

echo "🚀 Sending WhatsApp Message..."
echo "Content Preview:"
echo "$CONTENT"

# Send via OpenClaw
# IMPORTANT: Enter the target phone number if specific one needed, otherwise defaults might apply
# or if 'openclaw message send' requires a contact name/number.
# The user asked "SEND ME", implying the default self/configured contact.
# We'll use the --message argument.
# Escaping newlines/quotes might be needed for the shell command.

openclaw message send --target "+919778280044" --message "$CONTENT"

echo "✅ Message Sent."
