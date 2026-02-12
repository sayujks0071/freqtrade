#!/usr/bin/env python3
import json
import os
import sys


# Try to import ccxt, handle failure if not installed (e.g. running on host without venv)
try:
    import ccxt
except ImportError:
    print(
        "ERROR: ccxt not installed. Run 'pip install ccxt' or run inside Docker.", file=sys.stderr
    )
    sys.exit(1)


def main():
    delta_env = os.environ.get("DELTA_ENV", "india_testnet")
    api_key = os.environ.get("DELTA_API_KEY", "")
    api_secret = os.environ.get("DELTA_API_SECRET", "")
    base_url_override = os.environ.get("DELTA_BASE_URL", "")

    # print(f"DEBUG: Initializing Delta for env: {delta_env}", file=sys.stderr)

    config = {
        "apiKey": api_key,
        "secret": api_secret,
        "enableRateLimit": True,
        "options": {
            "defaultType": "swap",  # futures/swap
            "adjustForTimeDifference": True,
        },
    }

    # URL Overrides
    if base_url_override:
        config["urls"] = {"api": {"public": base_url_override, "private": base_url_override}}
    else:
        if delta_env == "india_prod":
            url = "https://api.india.delta.exchange"
            config["urls"] = {"api": {"public": url, "private": url}}
        elif delta_env == "global_prod":
            url = "https://api.delta.exchange"
            # Default URLs usually fine for global
        elif delta_env == "india_testnet":
            url = "https://cdn-ind.testnet.deltaex.org"
            config["urls"] = {"api": {"public": url, "private": url}}

    try:
        # Initialize exchange
        if not hasattr(ccxt, "delta"):
            print("ERROR: ccxt.delta not found. Update ccxt.", file=sys.stderr)
            sys.exit(1)

        exchange = ccxt.delta(config)

        # Load markets
        # params={'type': 'swap'} ensures we get perps if defaultType doesn't cover it
        markets = exchange.load_markets(params={"type": "swap"})

        # Convert to list of dicts for output
        market_list = []
        for symbol, market in markets.items():
            # Ensure symbol is in the dict (usually is)
            market["symbol"] = symbol
            market_list.append(market)

        print(json.dumps(market_list, indent=4, default=str))

    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
