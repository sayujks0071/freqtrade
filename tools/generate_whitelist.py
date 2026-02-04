#!/usr/bin/env python3
import json
import sys
from pathlib import Path


def filter_markets(markets):
    whitelist = []

    # Check if markets is a list (direct list of markets) or dict (ccxt structure)
    data = markets
    if isinstance(markets, dict):
        if "markets" in markets:
            data = markets["markets"]
        else:
            # Fallback for some dumps
            data = markets.values()

    if isinstance(data, dict):
        data = data.values()

    for m in data:
        # Depending on dump format, m could be string or dict
        if isinstance(m, str):
            symbol = m
            # If it's just a string, we assume it's valid if in the list
            # But usually list-markets --print-json returns a list of dicts with details
            # If freqtrade list-markets returns just strings, we accept them.
            # But for Delta we want futures.
            if "/USDT:USDT" in symbol:
                whitelist.append(symbol)
            continue

        symbol = m.get("symbol", "")
        active = m.get("active", True)

        if not active:
            continue

        # Filter for USDT Futures on Delta (usually have :USDT suffix)
        if "/USDT:USDT" in symbol:
            whitelist.append(symbol)

    return sorted(list(set(whitelist)))


def main():
    if len(sys.argv) < 2:
        print("Usage: generate_whitelist.py <markets_json>", file=sys.stderr)
        sys.exit(1)

    input_file = Path(sys.argv[1])
    if not input_file.exists():
        print(f"Error: {input_file} not found.", file=sys.stderr)
        sys.exit(1)

    with input_file.open("r") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            print("Error: Invalid JSON.", file=sys.stderr)
            sys.exit(1)

    whitelist = filter_markets(data)

    # Output format for Freqtrade
    output_obj = {"exchange": {"pair_whitelist": whitelist}}

    print(json.dumps(output_obj, indent=4))


if __name__ == "__main__":
    main()
