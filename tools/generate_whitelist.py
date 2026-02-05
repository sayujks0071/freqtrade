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
        symbol = m["symbol"]

        if not m.get("active", True):
            continue

        if FILTER_MODE == "perps_usdt":
            if "/USDT:USDT" in symbol:
                whitelist.append(symbol)
        elif FILTER_MODE == "all_futures":
            if ":" in symbol: # Rough check for futures
                whitelist.append(symbol)
        elif FILTER_MODE == "allowlist_regex":
            if regex.match(symbol):
                whitelist.append(symbol)
        else:
            if "/USDT:USDT" in symbol:
                whitelist.append(symbol)

    return sorted(list(set(whitelist)))

def main():
    if len(sys.argv) < 2:
        print("Usage: generate_whitelist.py <markets_json>")
        sys.exit(1)

    with Path(sys.argv[1]).open() as f:
        data = json.load(f)

    if isinstance(data, dict) and "markets" in data:
        data = data["markets"]

    whitelist = filter_markets(data)
    output_obj = {"exchange": {"pair_whitelist": whitelist}}
    print(json.dumps(output_obj, indent=4))

if __name__ == "__main__":
    main()
