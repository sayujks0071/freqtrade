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

    print(f"Generating whitelist with mode: {FILTER_MODE}")
    if FILTER_MODE == "allowlist_regex":
        print(f"Using regex: {ALLOWLIST_REGEX}")

    for m in markets:
        symbol = m.get("symbol", "")
        if not symbol:
            continue

        # Basic active check
        if not m.get("active", True):
            continue

        # Filter logic
        if FILTER_MODE == "perps_usdt":
            # Check if quote is USDT and it's a perp (using symbol naming convention)
            # Standard Freqtrade/CCXT convention for USDT-margined perps is usually BASE/USDT:USDT
            if symbol.endswith("/USDT:USDT"):
                whitelist.append(symbol)
        elif FILTER_MODE == "all_futures":
            # Assume all in list are futures if we ran list-markets --trading-mode futures
            whitelist.append(symbol)
        elif FILTER_MODE == "allowlist_regex":
            if regex.search(symbol):
                whitelist.append(symbol)
        else:
            # Default to perps_usdt if unknown mode
            if symbol.endswith("/USDT:USDT"):
                whitelist.append(symbol)

    return sorted(list(set(whitelist)))


def main():
    if len(sys.argv) < 2:
        print("Usage: generate_whitelist.py <markets_json>")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    try:
        with input_path.open() as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error reading {input_path}: {e}")
        sys.exit(1)

    if isinstance(data, dict) and "markets" in data:
        data = data["markets"]
    elif not isinstance(data, list):
        print("Error: Input JSON must be a list or dict with 'markets' key")
        sys.exit(1)

    whitelist = filter_markets(data)
    print(f"Whitelisted {len(whitelist)} pairs.")

    # Generate output filenames based on env or default
    env_name = os.environ.get("DELTA_ENV", "unknown")

    # JSON for config
    json_path = Path(f"user_data/pairlists/whitelist.delta.{env_name}.json")
    json_path.parent.mkdir(parents=True, exist_ok=True)

    # TXT for reference
    txt_path = Path(f"user_data/pairlists/whitelist.delta.{env_name}.txt")

    # Write JSON
    # JSONPairList expects a JSON list of strings or dict with "pairs" key.

    # Let's write just the list.
    with json_path.open("w") as f:
        json.dump(whitelist, f, indent=4)
    print(f"Written {json_path}")

    # Write TXT
    with txt_path.open("w") as f:
        for pair in whitelist:
            f.write(f"{pair}\n")
    print(f"Written {txt_path}")

    # Also output to stdout for piping if needed
    # print(json.dumps(whitelist))


if __name__ == "__main__":
    main()
