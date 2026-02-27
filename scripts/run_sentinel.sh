#!/bin/bash
# Wrapper to run Sentinel every 5 minutes
# Usage: ./scripts/run_sentinel.sh &

while true; do
    echo "[$(date)] Running Sentinel Check..."
    python3 scripts/sentinel.py

    # Wait 5 minutes
    sleep 300
done
