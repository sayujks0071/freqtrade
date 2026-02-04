#!/usr/bin/env python3
import argparse
import json
import re
import sys


def filter_markets(markets, filter_mode, allowlist_regex):
    whitelist = []

    for m in markets:
        if not m.get("active"):
            continue

        symbol = m["symbol"]

        # Basic check for futures format if not strictly checking 'type'
        # But we assume the dump is from a fetch_markets call that might have already filtered, or not.
        # We rely on symbol format mostly for freqtrade.

        if filter_mode == "perps_usdt":
            if symbol.endswith("/USDT:USDT"):
                whitelist.append(symbol)
        elif filter_mode == "all_futures":
            # Accept any valid futures symbol
            whitelist.append(symbol)
        elif filter_mode == "allowlist_regex":
            if re.match(allowlist_regex, symbol):
                whitelist.append(symbol)

    whitelist.sort()
    return whitelist


def generate_whitelist(markets_file, filter_mode, allowlist_regex):
    with open(markets_file, "r") as f:
        markets_data = json.load(f)
        if isinstance(markets_data, dict):
            markets = list(markets_data.values())
        else:
            markets = markets_data

    return filter_markets(markets, filter_mode, allowlist_regex)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--markets", required=True)
    parser.add_argument("--filter-mode", required=True)
    parser.add_argument("--allowlist-regex", default=".*")
    parser.add_argument("--output", required=True)
    parser.add_argument("--output-txt")

    args = parser.parse_args()

    whitelist = generate_whitelist(args.markets, args.filter_mode, args.allowlist_regex)

    with open(args.output, "w") as f:
        json.dump(whitelist, f, indent=4)

    if args.output_txt:
        with open(args.output_txt, "w") as f:
            f.write("\n".join(whitelist))
