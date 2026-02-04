#!/usr/bin/env python3
import argparse
import json
import os

import ccxt


def fetch_markets(exchange_id, output_file, env="india_prod"):
    # Configure exchange
    ex_class = getattr(ccxt, exchange_id)

    # URL overrides based on env
    urls = {}
    if env == "india_prod":
        urls["api"] = {
            "public": "https://api.india.delta.exchange",
            "private": "https://api.india.delta.exchange",
        }
    elif env == "global_prod":
        urls["api"] = {
            "public": "https://api.delta.exchange",
            "private": "https://api.delta.exchange",
        }
    elif env == "india_testnet":
        urls["api"] = {
            "public": "https://cdn-ind.testnet.deltaex.org",
            "private": "https://cdn-ind.testnet.deltaex.org",
        }

    # Check for DELTA_BASE_URL override
    if os.environ.get("DELTA_BASE_URL"):
        base = os.environ["DELTA_BASE_URL"]
        urls["api"] = {"public": base, "private": base}

    exchange = ex_class({"urls": urls})

    print(f"Fetching markets from {exchange.urls['api']['public']}...")
    # Load markets
    try:
        markets = exchange.load_markets()
    except Exception as e:
        print(f"Error fetching markets: {e}")
        exit(1)

    # Filter for futures/swaps only
    # We only want to validate/use futures stack
    filtered_data = []
    for m in markets.values():
        # Check type. CCXT usually sets 'swap': True, 'future': True/False, 'option': True/False
        # Delta futures are usually 'swap' (Perpetual) or 'future' (Expiry)
        if m.get("swap") or m.get("future"):
            # Double check it's not an option
            if not m.get("option"):
                filtered_data.append(m)

    with open(output_file, "w") as f:
        json.dump(filtered_data, f, indent=4)

    print(f"Fetched {len(filtered_data)} futures/swap markets to {output_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--exchange", default="delta")
    parser.add_argument("--output", required=True)
    parser.add_argument("--env", default="india_prod")

    args = parser.parse_args()

    fetch_markets(args.exchange, args.output, args.env)
