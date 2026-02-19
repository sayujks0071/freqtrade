"""
Fetch Markets Tool
Fetches full market data from Delta Exchange using CCXT and dumps to JSON.
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

import ccxt


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True, help="Output JSON file")
    parser.add_argument("--sandbox", action="store_true", help="Use Testnet")
    args = parser.parse_args()

    # Determine Environment
    delta_env = os.environ.get("DELTA_ENV", "india_testnet")

    # CCXT Config
    config = {
        "timeout": 30000,
        "enableRateLimit": True,
    }

    # URL Overrides
    base_url = os.environ.get("DELTA_BASE_URL")
    if not base_url:
        if delta_env == "india_prod":
            base_url = "https://api.india.delta.exchange"
        elif delta_env == "global_prod":
            base_url = "https://api.delta.exchange"
        elif delta_env == "india_testnet":
            base_url = "https://cdn-ind.testnet.deltaex.org"
        else:
            base_url = "https://api.delta.exchange"

    if base_url:
        config["urls"] = {
            "api": {
                "public": base_url,
                "private": base_url,
            },
            "www": "https://www.delta.exchange",
        }

    logger.info(f"Connecting to Delta ({delta_env}) at {base_url}...")

    try:
        exchange = ccxt.delta(config)
        markets = exchange.load_markets()

        # Convert to list of dicts
        market_list = []
        for symbol, m in markets.items():
            # Ensure consistency for schema validator
            # We just need to ensure m contains the fields we expect or enrich it
            # The 'entry' variable was unused, so we just use 'm' directly
            # We can optionally validate here but the schema validator does that.

            # Just ensure contract field logic if needed, but 'm' usually has it.
            # Schema validator checks: symbol, base, quote, active, contract.
            if "contract" not in m:
                m["contract"] = m.get("future", False) or m.get("swap", False)

            market_list.append(m)

        logger.info(f"Fetched {len(market_list)} markets.")

        with args.output.open("w", encoding="utf-8") as f:
            json.dump(market_list, f, indent=2, default=str)

        logger.info(f"Dumped to {args.output}")

    except Exception as e:
        logger.error(f"Failed to fetch markets: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
