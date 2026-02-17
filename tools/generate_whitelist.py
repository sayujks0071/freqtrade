#!/usr/bin/env python3
"""
generate_whitelist.py

Generates a canonical sorted whitelist from a markets JSON dump based on filtering rules.
"""

import argparse
import json
import logging
import os
import re
import sys
from typing import Any, List

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(description="Generate whitelist from markets dump.")
    parser.add_argument("--markets", required=True, help="Path to markets JSON dump file")
    parser.add_argument("--out", required=True, help="Path to output whitelist JSON file")
    return parser.parse_args()


def load_json(filepath: str) -> Any:
    try:
        with open(filepath, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load JSON from {filepath}: {e}")
        sys.exit(1)


def is_eligible(market: dict, filter_mode: str, allowlist_regex: str) -> bool:
    symbol = market.get("symbol")
    if not symbol:
        return False

    # Active check
    if not market.get("active"):
        return False

    if filter_mode == "allowlist_regex":
        if not allowlist_regex:
            logger.warning("FILTER_MODE is allowlist_regex but ALLOWLIST_REGEX is empty.")
            return False
        return bool(re.match(allowlist_regex, symbol))

    # Common checks for perps/futures
    # Check if it's a futures contract
    # Freqtrade/CCXT structure varies. Look for 'contract': True or 'future': True, or 'linear'/'inverse'.
    is_contract = (
        market.get("contract", False) or market.get("future", False) or market.get("swap", False)
    )
    if not is_contract:
        # Some exchanges might not set this explicitly in all versions, checking type
        if market.get("type") not in ["swap", "future"]:
             return False

    # Check Quote Currency
    quote = market.get("quote", "")
    base = market.get("base", "")
    settle = market.get("settle", "")  # Freqtrade adds this or CCXT does

    if filter_mode == "perps_usdt":
        # Expect USDT quote and linear (usually USDT settle)
        if quote != "USDT":
            return False
        # Check settle currency if available (linear)
        # Some dumps might not have 'settle', assume quote if linear?
        # Freqtrade usually normalizes this.
        if settle and settle != "USDT":
            return False
        return True

    if filter_mode == "all_futures":
        return True

    return False


def main():
    args = parse_args()

    filter_mode = os.environ.get("FILTER_MODE", "perps_usdt")
    allowlist_regex = os.environ.get("ALLOWLIST_REGEX", "")

    logger.info(f"Generating whitelist with FILTER_MODE={filter_mode}")

    markets_data = load_json(args.markets)
    markets = []
    if isinstance(markets_data, dict):
        markets = list(markets_data.values())
    elif isinstance(markets_data, list):
        markets = markets_data

    whitelist = []
    for m in markets:
        if is_eligible(m, filter_mode, allowlist_regex):
            whitelist.append(m["symbol"])

    # Sort alphabetically
    whitelist.sort()

    # Write output
    try:
        with open(args.out, "w") as f:
            json.dump(whitelist, f, indent=4)
        logger.info(f"Generated whitelist with {len(whitelist)} pairs to {args.out}")
    except Exception as e:
        logger.error(f"Failed to write whitelist: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
