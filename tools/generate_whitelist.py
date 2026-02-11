#!/usr/bin/env python3
import json
import os
import re
import sys
from pathlib import Path


# Env
FILTER_MODE = os.environ.get("FILTER_MODE", "perps_usdt")
ALLOWLIST_REGEX = os.environ.get("ALLOWLIST_REGEX", ".*")


def load_markets(data):
    """
    Robustly extract markets list from data which might be:
    - a list of market dicts
    - a dict with 'markets' key (list of dicts)
    """
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if "markets" in data and isinstance(data["markets"], list):
            return data["markets"]
    return []


def get_filter_strategy():
    """
    Returns a filter function based on the configuration.
    """
    if FILTER_MODE == "all_futures":
        return lambda s: ":" in s
    elif FILTER_MODE == "allowlist_regex":
        try:
            regex = re.compile(ALLOWLIST_REGEX)
            return lambda s: regex.match(s) is not None
        except re.error as e:
            print(f"Invalid regex '{ALLOWLIST_REGEX}': {e}", file=sys.stderr)
            sys.exit(1)
    else:
        # Default: perps_usdt
        return lambda s: "/USDT:USDT" in s


def filter_markets(markets):
    whitelist = []
    should_include = get_filter_strategy()

    for m in markets:
        if not isinstance(m, dict):
            continue

        symbol = m.get("symbol")
        if not symbol:
            continue

        # Basic active check
        if not m.get("active", True):
            continue

        if should_include(symbol):
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
        print(f"Error loading markets file: {e}", file=sys.stderr)
        sys.exit(1)

    markets = load_markets(data)
    if not markets:
        print("No markets found in input file.", file=sys.stderr)
        # Output empty whitelist
        print(json.dumps({"exchange": {"pair_whitelist": []}}, indent=4))
        return

    whitelist = filter_markets(markets)

    # JSON format for Freqtrade inclusion
    output_obj = {"exchange": {"pair_whitelist": whitelist}}

    print(json.dumps(output_obj, indent=4))


if __name__ == "__main__":
    main()
