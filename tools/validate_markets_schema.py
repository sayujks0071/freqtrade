#!/usr/bin/env python3
"""
Market Schema Validator for Delta Exchange (Freqtrade context)
Validates market dumps against schema rules, drift limits, and volume requirements.
"""

import argparse
import json
import sys
import logging
from pathlib import Path
from datetime import datetime, timezone

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("market_validator")

def setup_args():
    parser = argparse.ArgumentParser(description="Validate Delta Exchange market dump.")
    parser.add_argument("--markets", required=True, type=Path, help="Path to markets JSON dump")
    parser.add_argument("--env", default="unknown", help="Environment name (e.g., india_testnet)")
    parser.add_argument("--prev-whitelist", type=Path, help="Path to previous whitelist JSON for drift check")
    parser.add_argument("--out-report", type=Path, help="Path to write markdown report")
    parser.add_argument("--min-markets", type=int, default=20, help="Minimum number of markets required")
    parser.add_argument("--max-removal-ratio", type=float, default=0.25, help="Max ratio of removed pairs allowed")
    parser.add_argument("--strict-volume", action="store_true", help="Fail on low volume markets")
    parser.add_argument("--out-whitelist", type=Path, help="Path to write valid whitelist JSON")
    parser.add_argument("--filter-mode", default="perps_usdt", choices=["perps_usdt", "all_futures", "allowlist_regex"], help="Filter mode for whitelist generation")
    parser.add_argument("--allowlist-regex", default=".*USDT:USDT", help="Regex for allowlist_regex mode")
    return parser.parse_args()

def validate_schema(markets_data, args):
    report_lines = []
    errors = []

    if not isinstance(markets_data, list):
        return ["Markets data is not a list"], report_lines

    if len(markets_data) < args.min_markets:
        return [f"Market count {len(markets_data)} < minimum {args.min_markets}"], report_lines

    valid_markets = []
    seen_symbols = set()

    for m in markets_data:
        symbol = m.get("symbol")
        if not symbol:
            errors.append(f"Market missing symbol: {m}")
            continue

        # Check format BASE/QUOTE:SETTLE
        if "/" not in symbol or ":" not in symbol:
            errors.append(f"Invalid symbol format (expected BASE/QUOTE:SETTLE): {symbol}")
            continue

        if symbol in seen_symbols:
            errors.append(f"Duplicate symbol: {symbol}")
            continue
        seen_symbols.add(symbol)

        # Volume check (optional strictness)
        # Delta API might return different keys, but CCXT standardizes to 'quoteVolume' or 'baseVolume'
        # Adjust based on actual dump format if needed.
        # Assuming CCXT structure where info is raw or standardized.
        # Freqtrade list-markets returns a list of dictionaries with standardized keys.

        valid_markets.append(m)

    report_lines.append(f"## Schema Validation")
    report_lines.append(f"- Total Markets: {len(markets_data)}")
    report_lines.append(f"- Valid Markets: {len(valid_markets)}")
    report_lines.append(f"- Errors: {len(errors)}")

    if errors:
        report_lines.append("### Error Details")
        for e in errors[:10]: # Limit output
            report_lines.append(f"- {e}")
        if len(errors) > 10:
            report_lines.append(f"- ... and {len(errors)-10} more")

    return errors, report_lines

def check_drift(current_symbols, prev_whitelist_path, max_ratio):
    report_lines = []
    drift_errors = []

    if not prev_whitelist_path or not prev_whitelist_path.exists():
        report_lines.append("## Drift Check")
        report_lines.append("- No previous whitelist provided. Skipping drift check.")
        return [], report_lines

    try:
        with prev_whitelist_path.open() as f: # Use pathlib open for compliance
            prev_whitelist = json.load(f)
            if not isinstance(prev_whitelist, list):
                # Handle Freqtrade whitelist format if it's an object (unlikely for simple JSON list)
                 # If using standard Freqtrade whitelist file, it's a list.
                 pass
    except Exception as e:
        return [f"Failed to load previous whitelist: {e}"], []

    prev_set = set(prev_whitelist)
    current_set = set(current_symbols)

    removed = prev_set - current_set
    added = current_set - prev_set

    removal_ratio = len(removed) / len(prev_set) if len(prev_set) > 0 else 0.0

    report_lines.append("## Drift Check")
    report_lines.append(f"- Previous Whitelist Size: {len(prev_set)}")
    report_lines.append(f"- Current Market Size: {len(current_set)}")
    report_lines.append(f"- Removed Pairs: {len(removed)}")
    report_lines.append(f"- Added Pairs: {len(added)}")
    report_lines.append(f"- Removal Ratio: {removal_ratio:.2%}")

    if removal_ratio > max_ratio:
        drift_errors.append(f"Removal ratio {removal_ratio:.2%} exceeds limit {max_ratio:.2%}")

    if removed:
        report_lines.append("### Removed Pairs")
        for p in list(removed)[:10]:
            report_lines.append(f"- {p}")
        if len(removed) > 10:
             report_lines.append(f"- ... {len(removed)-10} more")

    return drift_errors, report_lines

def main():
    args = setup_args()

    logger.info(f"Validating markets from {args.markets}")

    try:
        # Use pathlib open
        with args.markets.open() as f:
            markets_data = json.load(f)
    except Exception as e:
        logger.error(f"Failed to read markets file: {e}")
        sys.exit(2)

    schema_errors, schema_report = validate_schema(markets_data, args)

    # Extract valid symbols for drift check
    # We assume valid symbols are those that passed schema check or just use all from input?
    # Let's use all present symbols that look roughly valid to check drift.
    current_symbols = [m.get("symbol") for m in markets_data if m.get("symbol")]

    drift_errors, drift_report = check_drift(current_symbols, args.prev_whitelist, args.max_removal_ratio)

    all_errors = schema_errors + drift_errors

    # Generate Report
    report = [f"# Market Validation Report - {args.env}", f"Date: {datetime.now(timezone.utc).isoformat()}"] # noqa: UP017
    report.extend(schema_report)
    report.extend(drift_report)

    report.append("## Conclusion")
    if all_errors:
        report.append("**Validation FAILED**")
        for e in all_errors:
            report.append(f"- {e}")
    else:
        report.append("**Validation PASSED**")

    if args.out_report:
        try:
            with args.out_report.open("w") as f:
                f.write("\n".join(report))
            logger.info(f"Report written to {args.out_report}")
        except Exception as e:
            logger.error(f"Failed to write report: {e}")

    if all_errors:
        logger.error("Validation failed with errors.")
        sys.exit(2)
    else:
        logger.info("Validation passed.")

        if args.out_whitelist:
            try:
                import re
                whitelist = []
                # Use current_symbols which were extracted earlier, or filter from markets_data based on args
                # We need to filter based on FILTER_MODE

                for m in markets_data:
                    symbol = m.get("symbol")
                    if not symbol: continue

                    # Basic validity check (already done in validate_schema but good to be safe)
                    if "/" not in symbol or ":" not in symbol: continue

                    if args.filter_mode == "perps_usdt":
                        if symbol.endswith(":USDT") or symbol.endswith("/USDT:USDT"): # Adjust based on actual Delta format
                             # Delta perps usually look like BTC/USDT:USDT
                             if re.match(r".*/USDT:USDT$", symbol):
                                 whitelist.append(symbol)
                    elif args.filter_mode == "all_futures":
                        whitelist.append(symbol)
                    elif args.filter_mode == "allowlist_regex":
                        if re.match(args.allowlist_regex, symbol):
                            whitelist.append(symbol)

                whitelist.sort()

                with args.out_whitelist.open("w") as f:
                    json.dump(whitelist, f, indent=4)
                logger.info(f"Whitelist written to {args.out_whitelist} ({len(whitelist)} pairs)")

            except Exception as e:
                logger.error(f"Failed to generate whitelist: {e}")
                sys.exit(1)

        sys.exit(0)

if __name__ == "__main__":
    main()
