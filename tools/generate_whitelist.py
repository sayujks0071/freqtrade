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

    print(f"Generating whitelist with FILTER_MODE={FILTER_MODE}")

    for m in markets:
        symbol = m.get("symbol")
        if not symbol:
            continue

        # Basic active check
        if not m.get("active", True):
            continue

        # Filter logic
        if FILTER_MODE == "perps_usdt":
            # Check if quote is USDT and it's a linear perp (usually :USDT suffix)
            if "/USDT:USDT" in symbol:
                whitelist.append(symbol)
        elif FILTER_MODE == "all_futures":
            # Assume all valid futures pairs passed validation
            whitelist.append(symbol)
        elif FILTER_MODE == "allowlist_regex":
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

    try:
        with Path(sys.argv[1]).open() as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error loading markets file: {e}")
        sys.exit(1)

    if isinstance(data, dict) and "markets" in data:
        data = data["markets"]

    whitelist = filter_markets(data)
    print(f"Generated whitelist with {len(whitelist)} pairs.")

    # Output paths
    json_out = Path("user_data/pairlists/whitelist.delta.json")
    txt_out = Path("user_data/pairlists/whitelist.delta.txt")

    # JSON format for Freqtrade inclusion
    output_obj = {"exchange": {"pair_whitelist": whitelist}}

    with json_out.open("w") as f:
        json.dump(output_obj, f, indent=4)

    with txt_out.open("w") as f:
        for pair in whitelist:
            f.write(f"{pair}\n")

    print(f"Saved to {json_out} and {txt_out}")


if __name__ == "__main__":
    main()
