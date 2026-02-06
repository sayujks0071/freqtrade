#!/usr/bin/env python3
import json
import os
import re
import sys
from pathlib import Path


# Env
FILTER_MODE = os.environ.get("FILTER_MODE", "perps_usdt")
ALLOWLIST_REGEX = os.environ.get("ALLOWLIST_REGEX", ".*USDT")


def filter_markets(markets):
    whitelist = []
    try:
        regex = re.compile(ALLOWLIST_REGEX)
    except re.error as e:
        print(f"Invalid Regex: {e}", file=sys.stderr)
        sys.exit(1)

    for m in markets:
        symbol = m.get("symbol")
        if not symbol:
            continue

        # Basic active check
        if not m.get("active", True):
            continue

        # Filter logic
        if FILTER_MODE == "perps_usdt":
            # Check if quote is USDT and it's a perp
            # In ccxt/freqtrade, futures usually have 'linear' type or swap
            # For Delta, we look for /USDT:USDT suffix which is standard CCXT notation for
            # linear perp
            if symbol.endswith("/USDT:USDT"):
                whitelist.append(symbol)
        elif FILTER_MODE == "all_futures":
            # Assuming the dump only contains futures as requested via
            # list-markets --trading-mode futures
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
        print("Usage: generate_whitelist.py <markets_json> [output_format: json|text]")
        sys.exit(1)

    input_file = sys.argv[1]
    output_format = sys.argv[2] if len(sys.argv) > 2 else "json"

    with Path(input_file).open() as f:
        data = json.load(f)

    if isinstance(data, dict):
        if "markets" in data:
            data = data["markets"]
        elif "pairs" in data:
            data = data["pairs"]

    whitelist = filter_markets(data)

    if output_format == "text":
        for p in whitelist:
            print(p)
    else:
        # JSON format for Freqtrade inclusion
        # We output a full config snippet that can be merged or loaded
        output_obj = {"exchange": {"pair_whitelist": whitelist}}
        print(json.dumps(output_obj, indent=4))


if __name__ == "__main__":
    main()
