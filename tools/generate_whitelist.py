#!/usr/bin/env python3
import json
import os
import re
import sys
from pathlib import Path


def main():
    if len(sys.argv) < 2:
        print("Usage: generate_whitelist.py <markets_file>")
        sys.exit(1)

    markets_file = sys.argv[1]

    FILTER_MODE = os.environ.get("FILTER_MODE", "perps_usdt")
    ALLOWLIST_REGEX = os.environ.get("ALLOWLIST_REGEX", ".*")

    with Path(markets_file).open() as f:
        markets = json.load(f)

    whitelist = []

    for m in markets:
        # Only consider active markets
        if not m.get("active"):
            continue

        symbol = m["symbol"]

        # Determine if it's a derivative
        is_contract = (
            m.get("contract", False)
            or m.get("linear", False)
            or m.get("inverse", False)
            or m.get("swap", False)
            or m.get("future", False)
        )
        quote = m.get("quote", "")

        if FILTER_MODE == "perps_usdt":
            # Must be a contract, quote USDT, and standard Delta format ending in :USDT
            if is_contract and quote == "USDT" and symbol.endswith(":USDT"):
                whitelist.append(symbol)
        elif FILTER_MODE == "all_futures":
            if is_contract:
                whitelist.append(symbol)
        elif FILTER_MODE == "allowlist_regex":
            if re.match(ALLOWLIST_REGEX, symbol):
                whitelist.append(symbol)
        else:
            # Default fallback: perps_usdt behavior
            if is_contract and quote == "USDT" and symbol.endswith(":USDT"):
                whitelist.append(symbol)

    # Sort canonical
    whitelist.sort()

    # Output as Freqtrade configuration
    output = {"exchange": {"pair_whitelist": whitelist}}

    print(json.dumps(output, indent=4))


if __name__ == "__main__":
    main()
