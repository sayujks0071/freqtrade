#!/usr/bin/env python3
import json
import os
import re
import sys
from pathlib import Path


def filter_markets(markets, filter_mode="perps_usdt", allowlist_regex=".*"):
    whitelist = []
    regex = re.compile(allowlist_regex)

    for m in markets:
        symbol = m.get("symbol", "")
        if not symbol:
            continue

        # Basic active check
        if not m.get("active", True):
            continue

        # Filter logic
        if filter_mode == "perps_usdt":
            # Check if quote is USDT and it's a perp
            # In ccxt/freqtrade, futures usually have 'linear' type or swap
            # We rely on symbol string mostly for Freqtrade
            if "/USDT:USDT" in symbol:
                whitelist.append(symbol)
        elif filter_mode == "all_futures":
            whitelist.append(symbol)
        elif filter_mode == "allowlist_regex":
            if regex.match(symbol):
                whitelist.append(symbol)
        else:
            # Default to perps_usdt
            if "/USDT:USDT" in symbol:
                whitelist.append(symbol)

    return sorted(list(set(whitelist)))


def main():
    if len(sys.argv) < 2:
        print("Usage: generate_whitelist.py <markets_json>")
        sys.exit(1)

    # Env
    filter_mode = os.environ.get("FILTER_MODE", "perps_usdt")
    allowlist_regex = os.environ.get("ALLOWLIST_REGEX", ".*")

    with Path(sys.argv[1]).open() as f:
        data = json.load(f)

    if isinstance(data, dict) and "markets" in data:
        data = data["markets"]

    whitelist = filter_markets(data, filter_mode=filter_mode, allowlist_regex=allowlist_regex)

    # Output format for freqtrade config (or just list)
    # JSON format for Freqtrade inclusion
    output_obj = {"exchange": {"pair_whitelist": whitelist}}

    print(json.dumps(output_obj, indent=4))


if __name__ == "__main__":
    main()
