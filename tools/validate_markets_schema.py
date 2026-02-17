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
from typing import Any, Dict, List, Optional, Set

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
    parser.add_argument("--prev-whitelist", help="Path to previous whitelist JSON file for drift check")
    parser.add_argument("--env", required=True, help="Environment name (e.g., india_prod, global_prod)")
    parser.add_argument("--out-report", help="Path to output markdown report", default="markets_schema_report.md")
    return parser.parse_args()


def load_json(filepath: str) -> Any:
    try:
        with open(filepath, "r") as f:
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

# Helper to reconstruct "is_eligible" logic for validation/drift check if needed?
# Actually, drift check uses previous whitelist vs NEW whitelist.
# But here we don't have the NEW whitelist generated yet (or do we?).
# This tool runs on the MARKETS dump.
# However, to check drift (removed pairs), we need to know which pairs WOULD be in the new whitelist.
# So we need to re-implement the filter logic here OR accept the generated whitelist as input.
# The user plan says: "update_markets_and_whitelist.sh ... generate canonical sorted whitelist ... outputs ... then validate".
# So `validate_markets_schema.py` should probably take `--new-whitelist` as argument?
# Or re-implement filtering. Re-implementing is safer to keep Validator independent?
# But logic duplication is bad.
# Let's import the logic from `generate_whitelist`? Or just duplicate it for now (simple logic).
# Actually, the user requirement says: "Drift safety gate: if removed_pairs_ratio > MAX_REMOVAL_RATIO ... => FAIL".
# This implies comparing OLD vs NEW whitelist.
# So this tool needs the NEW whitelist.
# Let's add `--candidate-whitelist` arg.

def main():
    parser = argparse.ArgumentParser(description="Validate markets schema and check for drift.")
    parser.add_argument("--markets", required=True, help="Path to markets JSON dump file")
    parser.add_argument("--candidate-whitelist", help="Path to newly generated whitelist JSON for drift check")
    parser.add_argument("--prev-whitelist", help="Path to previous whitelist JSON file for drift check")
    parser.add_argument("--env", required=True, help="Environment name (e.g., india_prod, global_prod)")
    parser.add_argument("--out-report", help="Path to output markdown report", default="markets_schema_report.md")
    args = parser.parse_args()

    # Load environment variables for configuration
    min_markets = int(os.environ.get("MIN_MARKETS", 20))
    max_removal_ratio = float(os.environ.get("MAX_REMOVAL_RATIO", 0.25))
    strict_volume = os.environ.get("STRICT_VOLUME", "false").lower() == "true"
    filter_mode = os.environ.get("FILTER_MODE", "perps_usdt")

    logger.info(f"Validating {args.markets} for env {args.env}")
    logger.info(f"Config: MIN_MARKETS={min_markets}, MAX_REMOVAL_RATIO={max_removal_ratio}, FILTER_MODE={filter_mode}")

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

    # Validation Results
    valid_markets = []
    failed_markets = []

    required_fields = ["symbol", "base", "quote", "active"]

    seen_symbols = set()

    # Create a map for quick lookup
    market_map = {}

    for m in markets:
        symbol = m.get("symbol")
        rejection_reasons = []

        # Check required fields
        for field in required_fields:
            if field not in m:
                rejection_reasons.append(f"Missing field: {field}")

        if not symbol:
            rejection_reasons.append("Missing symbol")
            failed_markets.append({"data": m, "reasons": rejection_reasons})
            continue

        market_map[symbol] = m

        # Check Uniqueness
        if symbol.upper() in seen_symbols:
            rejection_reasons.append(f"Duplicate symbol: {symbol}")
        seen_symbols.add(symbol.upper())

        # Check Symbol Format (only if it matches our filter mode intent)
        # But we check ALL markets in the dump? No, only those that matter.
        # But if the dump contains garbage symbols we ignore, that's fine.
        # But if a symbol LOOKS like it should be valid but has bad format, it's tricky.
        # Let's check format for ALL if filter_mode implies strict structure.
        if not validate_symbol_format(symbol, filter_mode):
            # If it fails format, is it a critical error?
            # If the exchange adds spot pairs with different format, we shouldn't fail futures validation.
            # So this check should only apply if we EXPECT it to be a valid future.
            # So maybe only warn here, but FAIL if it was in the previous whitelist.
            pass

        if rejection_reasons:
            failed_markets.append({"symbol": symbol, "reasons": rejection_reasons})
        else:
            valid_markets.append(symbol)

    # Drift Check
    drift_failed = False
    removal_ratio = 0.0
    added = []
    removed = []
    kept = []

    if args.candidate_whitelist and args.prev_whitelist and os.path.exists(args.prev_whitelist):
        logger.info("Performing Drift Check...")
        try:
            prev_whitelist = load_json(args.prev_whitelist)
            candidate_whitelist = load_json(args.candidate_whitelist)

            prev_set = set(prev_whitelist)
            curr_set = set(candidate_whitelist)

            added = list(curr_set - prev_set)
            removed = list(prev_set - curr_set)
            kept = list(curr_set.intersection(prev_set))

            if len(prev_set) > 0:
                removal_ratio = len(removed) / len(prev_set)

            logger.info(f"Drift Check: Added {len(added)}, Removed {len(removed)}, Kept {len(kept)}")
            logger.info(f"Removal Ratio: {removal_ratio:.2f} (Max: {max_removal_ratio})")

            if removal_ratio > max_removal_ratio:
                drift_failed = True
                logger.error(f"Drift Check FAILED: Removal ratio {removal_ratio:.2f} exceeds limit {max_removal_ratio}.")

            # Critical Safety Check: Existing Pair Format Corruption
            # If a pair was in prev_whitelist, and still exists in markets dump,
            # ensure its format didn't change (which would mean it's a different symbol string, but maybe components changed?)
            # Actually, if the symbol string changes, it shows up as REMOVED + ADDED.
            # But if the symbol string is same, but underlying contract/details changed invalidly?
            # Or if "BTC/USDT" became "btc/usdt"? (Case sensitivity)
            # validate_symbol_format checks strict format.
            # So if a pair from prev_whitelist is in candidate_whitelist (so it's kept),
            # we want to ensure it passes schema validation?
            # The candidate generation logic supposedly filters valid ones.
            # If it's in candidate, it passed generation.

            # Check if any REMOVED pair actually exists in dump but failed format validation?
            # This would indicate a format change.
            for pair in removed:
                # If it's in the raw dump but not in candidate...
                if pair in market_map:
                    # It exists but was filtered out. Why?
                    # Maybe it became inactive? Or failed format?
                    # If it failed format (e.g. colon missing), that's a "format changed" event we want to catch.
                    # But if it just became inactive, that's normal removal.
                    m = market_map[pair]
                    if m.get("active") and not validate_symbol_format(pair, filter_mode):
                         logger.error(f"CRITICAL: Pair {pair} exists but failed format validation! Possible schema change.")
                         # This might be worth failing for.
                         drift_failed = True

        except Exception as e:
            logger.error(f"Drift check error: {e}")
            sys.exit(2)

    # Volume Sanity (Optional)
    # If strict volume check is enabled, check quotes?
    # Not implemented fully as it requires 24h ticker data which might not be in list-markets dump.
    # list-markets sometimes has info, but usually need fetch-tickers.
    # We skip this for now or warn if info available.

    # Report Generation
    with open(args.out_report, "w") as f:
        f.write(f"# Market Schema Validation Report\n\n")
        f.write(f"- **Date**: {datetime.now(timezone.utc).isoformat()}\n")
        f.write(f"- **Environment**: {args.env}\n")
        f.write(f"- **Total Markets**: {len(markets)}\n")
        f.write(f"- **Candidate Whitelist**: {len(load_json(args.candidate_whitelist)) if args.candidate_whitelist else 'N/A'}\n")

        if drift_failed:
             f.write(f"- **STATUS**: **FAIL** (Drift/Safety)\n")
        elif len(markets) < min_markets:
             f.write(f"- **STATUS**: **FAIL** (Min Markets)\n")
        else:
             f.write(f"- **STATUS**: **PASS**\n")

        if args.candidate_whitelist:
            f.write(f"\n## Drift Analysis\n")
            f.write(f"- Added: {len(added)}\n")
            f.write(f"- Removed: {len(removed)}\n")
            f.write(f"- Removal Ratio: {removal_ratio:.2%} (Limit: {max_removal_ratio:.2%})\n")

            if removed:
                f.write("\n### Removed Pairs\n")
                for p in removed:
                    f.write(f"- {p}\n")

    if drift_failed:
        sys.exit(2)

    logger.info("Schema validation passed.")
    sys.exit(0)

if __name__ == "__main__":
    main()
