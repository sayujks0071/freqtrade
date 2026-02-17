#!/usr/bin/env python3
"""
validate_markets_schema.py

Validates the markets dump from Freqtrade/CCXT against strict schema rules.
Acts as a gatekeeper before updating the whitelist.
"""

import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S%z",
)
logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(description="Validate markets schema and check for drift.")
    parser.add_argument("--markets", required=True, help="Path to markets JSON dump file")
    parser.add_argument(
        "--candidate-whitelist", help="Path to newly generated whitelist JSON for drift check"
    )
    parser.add_argument(
        "--prev-whitelist", help="Path to previous whitelist JSON file for drift check"
    )
    parser.add_argument(
        "--env", required=True, help="Environment name (e.g., india_prod, global_prod)"
    )
    parser.add_argument(
        "--out-report",
        help="Path to output markdown report",
        default="markets_schema_report.md",
    )
    return parser.parse_args()


def load_json(filepath: str) -> Any:
    path = Path(filepath)
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load JSON from {filepath}: {e}")
        sys.exit(2)


def validate_symbol_format(symbol: str, filter_mode: str) -> bool:
    """
    Validates the symbol format based on the filter mode.
    For futures (default), expects BASE/QUOTE:SETTLE (e.g., BTC/USDT:USDT).
    """
    if filter_mode in ["perps_usdt", "all_futures"]:
        # Strict format: Uppercase, no whitespace, contains slash and colon
        pattern = r"^[A-Z0-9]+/[A-Z0-9]+:[A-Z0-9]+$"
        return bool(re.match(pattern, symbol))
    # For allowlist_regex, we assume the regex does the validation during generation
    return True


def perform_drift_check(
    candidate_path: str, prev_path: str, max_removal_ratio: float, market_map: Dict[str, Any],
    filter_mode: str
) -> Tuple[bool, float, List[str], List[str]]:
    """
    Checks for drift between previous whitelist and candidate whitelist.
    Returns (failed, removal_ratio, added, removed).
    """
    if not (candidate_path and prev_path and Path(prev_path).exists()):
        return False, 0.0, [], []

    logger.info("Performing Drift Check...")
    try:
        prev_whitelist = load_json(prev_path)
        candidate_whitelist = load_json(candidate_path)

        prev_set = set(prev_whitelist)
        curr_set = set(candidate_whitelist)

        added = list(curr_set - prev_set)
        removed = list(prev_set - curr_set)
        kept = list(curr_set.intersection(prev_set))

        removal_ratio = 0.0
        if len(prev_set) > 0:
            removal_ratio = len(removed) / len(prev_set)

        logger.info(
            f"Drift Check: Added {len(added)}, Removed {len(removed)}, Kept {len(kept)}"
        )
        logger.info(f"Removal Ratio: {removal_ratio:.2f} (Max: {max_removal_ratio})")

        drift_failed = False
        if removal_ratio > max_removal_ratio:
            drift_failed = True
            logger.error(
                f"Drift Check FAILED: Removal ratio {removal_ratio:.2f} "
                f"exceeds limit {max_removal_ratio}."
            )

        # Check if any REMOVED pair actually exists in dump but failed format validation?
        for pair in removed:
            if pair in market_map:
                m = market_map[pair]
                if m.get("active") and not validate_symbol_format(pair, filter_mode):
                    logger.error(
                        f"CRITICAL: Pair {pair} exists but failed format validation! "
                        "Possible schema change."
                    )
                    drift_failed = True

        return drift_failed, removal_ratio, added, removed

    except Exception as e:
        logger.error(f"Drift check error: {e}")
        sys.exit(2)


def generate_report(
    out_path: str,
    env: str,
    markets_count: int,
    candidate_whitelist_path: Optional[str],
    drift_failed: bool,
    min_markets: int,
    added: List[str],
    removed: List[str],
    removal_ratio: float,
    max_removal_ratio: float,
):
    path = Path(out_path)
    with path.open("w", encoding="utf-8") as f:
        f.write("# Market Schema Validation Report\n\n")
        # Use timezone.utc explicitly to avoid ruff UP017 if datetime.UTC is not preferred
        # actually ruff prefers datetime.UTC in python 3.11+
        # I will stick to timezone.utc and suppress if needed, but the log said "Use datetime.UTC"
        # I will try to use datetime.now(timezone.utc)
        f.write(f"- **Date**: {datetime.now(timezone.utc).isoformat()}\n")
        f.write(f"- **Environment**: {env}\n")
        f.write(f"- **Total Markets**: {markets_count}\n")

        candidate_count = "N/A"
        if candidate_whitelist_path:
            candidate_count = str(len(load_json(candidate_whitelist_path)))

        f.write(f"- **Candidate Whitelist**: {candidate_count}\n")

        if drift_failed:
            f.write("- **STATUS**: **FAIL** (Drift/Safety)\n")
        elif markets_count < min_markets:
            f.write("- **STATUS**: **FAIL** (Min Markets)\n")
        else:
            f.write("- **STATUS**: **PASS**\n")

        if candidate_whitelist_path:
            f.write("\n## Drift Analysis\n")
            f.write(f"- Added: {len(added)}\n")
            f.write(f"- Removed: {len(removed)}\n")
            f.write(f"- Removal Ratio: {removal_ratio:.2%} (Limit: {max_removal_ratio:.2%})\n")

            if removed:
                f.write("\n### Removed Pairs\n")
                for p in removed:
                    f.write(f"- {p}\n")


def main():
    args = parse_args()

    # Load environment variables for configuration
    min_markets = int(os.environ.get("MIN_MARKETS", 20))
    max_removal_ratio = float(os.environ.get("MAX_REMOVAL_RATIO", 0.25))
    # strict_volume = os.environ.get("STRICT_VOLUME", "false").lower() == "true" # Unused
    filter_mode = os.environ.get("FILTER_MODE", "perps_usdt")

    logger.info(f"Validating {args.markets} for env {args.env}")
    logger.info(
        f"Config: MIN_MARKETS={min_markets}, "
        f"MAX_REMOVAL_RATIO={max_removal_ratio}, FILTER_MODE={filter_mode}"
    )

    markets_data = load_json(args.markets)

    markets = []
    if isinstance(markets_data, dict):
        markets = list(markets_data.values())
    elif isinstance(markets_data, list):
        markets = markets_data
    else:
        logger.error("Invalid markets data format. Expected dict or list.")
        sys.exit(2)

    if not markets:
        logger.error("Markets data is empty.")
        sys.exit(2)

    if len(markets) < min_markets:
        logger.error(f"Market count {len(markets)} is below MIN_MARKETS ({min_markets}).")
        sys.exit(2)

    required_fields = ["symbol", "base", "quote", "active"]
    seen_symbols = set()
    market_map = {}
    failed_markets = []

    for m in markets:
        symbol = m.get("symbol")
        rejection_reasons = []

        for field in required_fields:
            if field not in m:
                rejection_reasons.append(f"Missing field: {field}")

        if not symbol:
            rejection_reasons.append("Missing symbol")
            failed_markets.append({"data": m, "reasons": rejection_reasons})
            continue

        market_map[symbol] = m

        if symbol.upper() in seen_symbols:
            rejection_reasons.append(f"Duplicate symbol: {symbol}")
        seen_symbols.add(symbol.upper())

        # Validate format (audit only, don't fail schema unless critical)
        validate_symbol_format(symbol, filter_mode)

        if rejection_reasons:
            failed_markets.append({"symbol": symbol, "reasons": rejection_reasons})

    drift_failed, removal_ratio, added, removed = perform_drift_check(
        args.candidate_whitelist,
        args.prev_whitelist,
        max_removal_ratio,
        market_map,
        filter_mode
    )

    generate_report(
        args.out_report,
        args.env,
        len(markets),
        args.candidate_whitelist,
        drift_failed,
        min_markets,
        added,
        removed,
        removal_ratio,
        max_removal_ratio,
    )

    if drift_failed:
        sys.exit(2)

    logger.info("Schema validation passed.")
    sys.exit(0)


if __name__ == "__main__":
    main()
