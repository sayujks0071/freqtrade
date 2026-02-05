#!/usr/bin/env python3
"""
Generate Whitelist from Market Dump
Reads a freqtrade list-markets JSON dump and outputs a whitelist config file.
"""

import json
import sys
from pathlib import Path


def generate_whitelist(market_file):
    try:
        with Path(market_file).open() as f:
            markets = json.load(f)

        whitelist = []
        for market in markets:
            # Basic filtering for Delta Futures
            # We want pairs settled in USDT, quoting USDT (usually)
            # Freqtrade symbols are BASE/QUOTE:SETTLE for futures.
            # Delta example: BTC/USDT:USDT

            symbol = market.get("symbol")
            if not symbol:
                continue

            # Check if active
            if not market.get("active", True):
                continue

            # Ensure it's a futures pair (this check depends on what list-markets returns)
            # If we ran list-markets with --trading-mode futures, they should be futures.
            # But double check if settlement is present.
            if ":" not in symbol:
                continue

            # Filter for USDT settlement if desired (usually safer default)
            if not symbol.endswith(":USDT"):
                continue

            # Exclude options if any sneak in (usually have -C- or -P-)
            if "-C-" in symbol or "-P-" in symbol:
                continue

            whitelist.append(symbol)

        # Generate config structure
        config = {
            "exchange": {
                "pair_whitelist": sorted(whitelist),
                "pair_blacklist": [
                    # Add common noise pairs or low volume ones here if known
                ],
            }
        }

        print(json.dumps(config, indent=4))

    except Exception as e:
        print(f"Error generating whitelist: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 generate_whitelist.py <market_file.json>", file=sys.stderr)
        sys.exit(1)

    generate_whitelist(sys.argv[1])
