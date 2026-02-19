"""
Generate Whitelist Tool
Filters market dump and generates Freqtrade whitelist config and text list.
"""

import argparse
import json
import logging
import os
import re
import sys
from pathlib import Path


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("markets_file", type=Path, help="Markets JSON dump")
    parser.add_argument("--out-json", type=Path, required=True, help="Output JSON config")
    parser.add_argument("--out-txt", type=Path, required=True, help="Output TXT list")
    args = parser.parse_args()

    filter_mode = os.environ.get("FILTER_MODE", "perps_usdt")
    allowlist_regex = os.environ.get("ALLOWLIST_REGEX", ".*")

    logger.info(f"Generating whitelist from {args.markets_file} (Mode: {filter_mode})")

    try:
        with args.markets_file.open("r") as f:
            markets = json.load(f)

        whitelist = []
        regex = re.compile(allowlist_regex)

        for m in markets:
            if not m.get("active"):
                continue

            symbol = m["symbol"]
            quote = m["quote"]
            contract = m.get("contract", False) or m.get("future", False) or m.get("swap", False)

            # Filter Logic
            if filter_mode == "perps_usdt":
                if contract and quote == "USDT" and regex.match(symbol):
                    whitelist.append(symbol)
            elif filter_mode == "all_futures":
                if contract and regex.match(symbol):
                    whitelist.append(symbol)
            elif filter_mode == "allowlist_regex":
                if regex.match(symbol):
                    whitelist.append(symbol)
            else:
                # Default fallback
                if contract and quote == "USDT":
                    whitelist.append(symbol)

        whitelist.sort()
        logger.info(f"Selected {len(whitelist)} pairs.")

        # Write JSON Config
        config = {"exchange": {"pair_whitelist": whitelist}}
        with args.out_json.open("w") as f:
            json.dump(config, f, indent=4)

        # Write TXT List
        with args.out_txt.open("w") as f:
            f.write("\n".join(whitelist))

    except Exception as e:
        logger.error(f"Failed to generate whitelist: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
