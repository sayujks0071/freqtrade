"""
Fetch Markets Tool
Fetches full market data from Delta Exchange using CCXT and dumps to JSON.
"""

import argparse
import json
import logging
import os
import sys
from datetime import UTC, datetime
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
    # Check for specific environment variables set by common.sh or docker-compose
    # Note: CCXT expects 'urls': {'api': ...}
    # We can rely on standard CCXT if DELTA_ENV matches standard delta URLs
    # But for India/Global split, we might need overrides.

    # If using freqtrade docker environment, these might be set.
    # But here we are running a standalone script.
    # Let's check environment vars.

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

    if args.sandbox or "testnet" in delta_env:
        # CCXT delta might not have 'set_sandbox_mode' or it might be different.
        # Delta testnet is usually just a different URL.
        pass

    logger.info(f"Connecting to Delta ({delta_env}) at {base_url}...")

    try:
        exchange = ccxt.delta(config)
        markets = exchange.load_markets()

        # Convert to list of dicts
        market_list = []
        for symbol, m in markets.items():
            # Add implicit fields if missing or ensure consistency
            entry = {
                "symbol": m["symbol"],
                "base": m["base"],
                "quote": m["quote"],
                "active": m["active"],
                "contract": m.get("contract", False) or m.get("future", False) or m.get("swap", False),
                "spot": m.get("spot", False),
                "details": m  # Full details if needed, but keeps file large
            }
            # Remove full details to keep it clean, or keep it?
            # Schema validator checks keys on the top level.
            # I will keep the full 'm' but ensure top level keys are accessible.
            # Actually, let's just dump the full 'm' but make sure required fields are there.
            # CCXT market structure usually has 'symbol', 'base', 'quote', 'active'.
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
