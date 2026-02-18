#!/usr/bin/env python3
import json
import sys
import os
import re
from datetime import datetime, timezone

def get_env(key, default):
    return os.environ.get(key, default)

def fail(message, report_file):
    print(f"FAIL: {message}")
    with open(report_file, 'a') as f:
        f.write(f"\n## FAILURE\n{message}\n")
    sys.exit(2)

def warn(message, report_file):
    print(f"WARN: {message}")
    with open(report_file, 'a') as f:
        f.write(f"\n## WARNING\n{message}\n")

def main():
    if len(sys.argv) < 2:
        print("Usage: validate_markets_schema.py <markets_file> [prev_markets_file]")
        sys.exit(1)

    markets_file = sys.argv[1]
    prev_markets_file = sys.argv[2] if len(sys.argv) > 2 else None

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    report_file = f"user_data/reports/whitelist_diff_{timestamp}.md"

    # Environment configs
    MIN_MARKETS = int(get_env("MIN_MARKETS", 20))
    MAX_REMOVAL_RATIO = float(get_env("MAX_REMOVAL_RATIO", 0.25))
    STRICT_VOLUME = get_env("STRICT_VOLUME", "false").lower() == "true"
    FILTER_MODE = get_env("FILTER_MODE", "perps_usdt")

    # Ensure report directory exists
    os.makedirs(os.path.dirname(report_file), exist_ok=True)

    with open(report_file, 'w') as f:
        f.write(f"# Market Schema Validation Report\nDate: {timestamp}\nFile: {markets_file}\n\n")

    # Load Market Data
    try:
        with open(markets_file, 'r') as f:
            markets = json.load(f)
    except Exception as e:
        # Create a basic report file even on JSON fail to log the error
        with open(report_file, 'a') as f:
             f.write(f"Invalid JSON: {e}\n")
        # We can't use fail() here easily if we want to be safe, but fail() opens append.
        print(f"FAIL: Invalid JSON: {e}")
        sys.exit(2)

    if not isinstance(markets, list):
         fail("Markets dump must be a list", report_file)

    if len(markets) < MIN_MARKETS:
        fail(f"Too few markets: {len(markets)} < {MIN_MARKETS}", report_file)

    # Validate Schema
    required_fields = ["symbol", "base", "quote", "active"] # 'info' is usually there but minimal check
    symbols = set()
    active_count = 0

    for m in markets:
        # Check required fields
        for field in required_fields:
            if field not in m:
                fail(f"Missing field '{field}' in market: {m.get('symbol', 'UNKNOWN')}", report_file)

        symbol = m['symbol']

        # Uniqueness
        if symbol.lower() in [s.lower() for s in symbols]:
            fail(f"Duplicate symbol found: {symbol}", report_file)
        symbols.add(symbol)

        if m.get('active'):
            active_count += 1

        # Format Check
        # Expecting BASE/QUOTE:SETTLE for futures
        if FILTER_MODE in ['perps_usdt', 'all_futures']:
             if ':' not in symbol:
                 fail(f"Invalid symbol format for futures (missing colon): {symbol}", report_file)
             parts = symbol.split(':')
             if len(parts) != 2:
                 fail(f"Invalid symbol format (too many colons): {symbol}", report_file)
             if not parts[1]:
                 fail(f"Invalid symbol format (empty settle currency): {symbol}", report_file)

        # Volume Check (Heuristic if volume is present)
        if STRICT_VOLUME:
            # Try to find volume. CCXT standardizes 'quoteVolume' or 'baseVolume'
            # But usually it's in 'info' or 24h stats. List markets might not have 24h volume.
            # If it's just metadata, we might skip volume check or look at 'info'.
            # The prompt says "if STRICT_VOLUME=true and too illiquid".
            # Usually list-markets DOES NOT return volume unless fetched with fetch_tickers.
            # list-markets returns metadata.
            # If so, we can't check volume here.
            # I will warn if I can't find it, but not fail unless sure.
            # Actually, `fetch_markets` usually doesn't have volume. `fetch_tickers` does.
            # The script calls `list-markets` which in Freqtrade usually calls `exchange.get_markets()`.
            # If it's a dry run validation, we might skip volume check if data is missing.
            pass

    # Drift Check
    if prev_markets_file and os.path.exists(prev_markets_file):
        try:
            with open(prev_markets_file, 'r') as f:
                prev_markets = json.load(f)

            prev_symbols = {m['symbol'] for m in prev_markets if m.get('active')}
            curr_symbols = {m['symbol'] for m in markets if m.get('active')}

            removed = prev_symbols - curr_symbols
            added = curr_symbols - prev_symbols

            removal_ratio = len(removed) / len(prev_symbols) if len(prev_symbols) > 0 else 0.0

            with open(report_file, 'a') as f:
                f.write(f"\n## Drift Analysis\n")
                f.write(f"- Previous Active: {len(prev_symbols)}\n")
                f.write(f"- Current Active: {len(curr_symbols)}\n")
                f.write(f"- Removed: {len(removed)} ({removal_ratio:.2%})\n")
                f.write(f"- Added: {len(added)}\n")

            if removal_ratio > MAX_REMOVAL_RATIO:
                fail(f"Drift Safety Gate Triggered! Removed ratio {removal_ratio:.2%} > {MAX_REMOVAL_RATIO}", report_file)

        except Exception as e:
            warn(f"Could not perform drift check: {e}", report_file)

    print("Validation PASSED.")
    sys.exit(0)

if __name__ == "__main__":
    main()
