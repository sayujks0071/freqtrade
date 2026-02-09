#!/usr/bin/env python3
import json
import os
import re
import sys
from pathlib import Path


# Env
FILTER_MODE = os.environ.get("FILTER_MODE", "perps_usdt")
ALLOWLIST_REGEX = os.environ.get("ALLOWLIST_REGEX", ".*")


def filter_markets(markets):
    whitelist = []
    regex = re.compile(ALLOWLIST_REGEX)

    for m in markets:
        symbol = m.get("symbol", "")
        if not symbol:
            continue

        # Basic active check
        if not m.get("active", True):
            continue

        # Filter logic
        if FILTER_MODE == "perps_usdt":
            # Check if quote is USDT and it's a perp
            # In Delta, symbols are usually BASE/USDT:USDT for perps
            if symbol.endswith("/USDT:USDT"):
                whitelist.append(symbol)
        elif FILTER_MODE == "all_futures":
             # All futures usually have a settle currency
            if ":" in symbol:
                whitelist.append(symbol)
        elif FILTER_MODE == "allowlist_regex":
            if regex.match(symbol):
                whitelist.append(symbol)
        else:
            # Default to perps_usdt
            if symbol.endswith("/USDT:USDT"):
                whitelist.append(symbol)

    return sorted(list(set(whitelist)))


def main():
    if len(sys.argv) < 2:
        print("Usage: generate_whitelist.py <markets_json>")
        sys.exit(1)

    try:
        with Path(sys.argv[1]).open() as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error reading input: {e}")
        sys.exit(1)

    # Normalize input
    if isinstance(data, dict) and "markets" in data:
        data = data["markets"]
    elif isinstance(data, list):
        pass # OK
    else:
        print("Invalid input format")
        sys.exit(1)

    whitelist = filter_markets(data)

    # JSON format for Freqtrade inclusion
    output_obj = {"exchange": {"pair_whitelist": whitelist}}

    print(json.dumps(output_obj, indent=4))


if __name__ == "__main__":
    main()
