#!/bin/bash
# Wrapper script to run Optimization and Notify User via OpenClaw
# Usage: ./run_opt_and_notify.sh

LOG_FILE="optimization_log.txt"

echo "🔔 Starting Optimization with Notifications..."
echo "Logs being written to $LOG_FILE"

# 1. Run Optimization Pipeline
./optimize_all_strategies.sh > $LOG_FILE 2>&1

EXIT_CODE=$?

# 2. Extract Results Summary (Simulated extraction of key metrics)
# In a real scenario, we'd parse the json files.
# For now, we'll grep the log for profit summaries if possible, or just link the file.

SUMMARY="Optimization Pipeline Complete.\n"

if [ $EXIT_CODE -eq 0 ]; then
    SUMMARY+="Status: ✅ SUCCESS\n"
    SUMMARY+="Strategies Optimized: MomentumVolumeTrend, BollingerRSI, VolatilityBreakout, MLPredictor\n"

    # Try to grab last Sharpe ratio or profit line from log if it exists in stdout
    # grep "Total profit" $LOG_FILE | tail -n 5
else
    SUMMARY+="Status: ❌ FAILED (Exit Code: $EXIT_CODE)\n"
    SUMMARY+="Check logs at $LOG_FILE\n"
fi

echo -e "$SUMMARY"

# 3. Send WhatsApp Notification via OpenClaw
# Assuming 'openclaw' command is configured and 'message send' works
# We'll use a simple text message.

echo "Sending WhatsApp Alert..."
openclaw message send --message "$SUMMARY"

echo "Done."
