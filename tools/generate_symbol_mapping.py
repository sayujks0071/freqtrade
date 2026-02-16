#!/usr/bin/env python3
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def generate_mapping(markets_file):
    try:
        with Path(markets_file).open("r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: File {markets_file} not found.", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"Error: File {markets_file} is not valid JSON.", file=sys.stderr)
        sys.exit(1)

    print("# Delta Symbol Mapping Report")
    print(f"Generated at: {datetime.now(timezone.utc).isoformat()}")  # noqa: UP017
    print(f"Source: {markets_file}")
    print("\n## Symbol Mapping")
    print("| Freqtrade Pair | Delta Contract Symbol | Type |")
    print("|---|---|---|")

    # Handle different formats (list of dicts or dict of dicts)
    # list-markets --print-json usually outputs a list of markets
    markets = []
    if isinstance(data, list):
        markets = data
    elif isinstance(data, dict):
        # Could be keyed by symbol
        markets = data.values()

    for market in markets:
        # Check if it looks like a market structure
        if not isinstance(market, dict):
            continue

        pair = market.get('symbol', 'N/A')
        contract = market.get('id', 'N/A')
        type_ = market.get('type', 'N/A')

        # Filter for Delta relevant pairs if needed (e.g. valid pairs only)
        # But report should show what's in the dump.

        print(f"| `{pair}` | `{contract}` | {type_} |")

    print("\n## Explanation")
    print(
        "- **Freqtrade Pair**: The format used in Freqtrade configuration and strategies "
        "(e.g., `BTC/USDT:USDT`)."
    )
    print(
        "- **Delta Contract Symbol**: The actual contract symbol on Delta Exchange "
        "(e.g., `BTCUSDT`)."
    )
    print("- **Type**: Spot or Future.")
    print("\n### Note")
    print("Always use the 'Freqtrade Pair' format in your whitelist and strategy configuration.")


def main():
    parser = argparse.ArgumentParser(
        description="Generate symbol mapping report from markets dump."
    )
    parser.add_argument("markets_file", help="Path to the markets JSON file")
    args = parser.parse_args()

    generate_mapping(args.markets_file)


if __name__ == "__main__":
    main()
