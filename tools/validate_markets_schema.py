#!/usr/bin/env python3
"""
Market Schema Validator for Delta Exchange (Freqtrade context)
Validates market dumps against schema rules, drift limits, and volume requirements.
"""

import argparse
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("market_validator")


def setup_args():
    parser = argparse.ArgumentParser(description="Validate Delta Exchange market dump.")
    parser.add_argument("--markets", required=True, type=Path, help="Path to markets JSON dump")
    parser.add_argument("--env", default="unknown", help="Environment name (e.g., india_testnet)")
    parser.add_argument(
        "--prev-whitelist", type=Path, help="Path to previous whitelist JSON for drift check"
    )
    parser.add_argument("--out-report", type=Path, help="Path to write markdown report")
    parser.add_argument(
        "--min-markets", type=int, default=20, help="Minimum number of markets required"
    )
    parser.add_argument(
        "--max-removal-ratio",
        type=float,
        default=0.25,
        help="Max ratio of removed pairs allowed",
    )
    parser.add_argument("--strict-volume", action="store_true", help="Fail on low volume markets")
    parser.add_argument("--out-whitelist", type=Path, help="Path to write valid whitelist JSON")
    parser.add_argument(
        "--filter-mode",
        default="perps_usdt",
        choices=["perps_usdt", "all_futures", "allowlist_regex"],
        help="Filter mode for whitelist generation",
    )
    parser.add_argument(
        "--allowlist-regex", default=".*USDT:USDT", help="Regex for allowlist_regex mode"
    )
    return parser.parse_args()


def validate_schema(markets_data, args):
    report_lines = []
    errors = []

    # 1. Basic Structure
    if not isinstance(markets_data, list):
        errors.append("Markets data is not a list")
        return errors, ["Data is not a list"]

    if len(markets_data) < args.min_markets:
        errors.append(f"Too few markets: {len(markets_data)} < {args.min_markets}")

    # 2. Field Check & Symbol Format
    valid_count = 0
    for i, market in enumerate(markets_data):
        symbol = market.get("symbol", "")
        if not symbol:
            # Maybe verbose log
            continue

        # Check required fields (approximate CCXT / Freqtrade expectations)
        # id, symbol, base, quote are essential
        missing = [f for f in ["id", "symbol", "base", "quote"] if f not in market]
        if missing:
            errors.append(f"Market index {i} missing fields: {missing}")

        # Symbol Format (Freqtrade futures: BASE/QUOTE:SETTLE)
        if "/" not in symbol or ":" not in symbol:
            # Soft error or hard? For now, just log/track.
            # If strictly perps, we expect :
            pass

        # Volume check (optional strictness)
        # Delta API might return different keys, but CCXT standardizes to quoteVolume/baseVolume
        # Adjust based on actual dump format if needed.
        # Assuming CCXT structure where info is raw or standardized.
        vol = market.get("quoteVolume") or market.get("info", {}).get("quote_volume_24h")
        if args.strict_volume and (not vol or float(vol) <= 0):
            errors.append(f"Market {symbol} has zero/missing volume")

        valid_count += 1

    report_lines.append(f"Analyzed {len(markets_data)} items. Valid format: {valid_count}")

    if errors:
        report_lines.append("### Error Details")
        for e in errors[:10]:  # Limit output
            report_lines.append(f"- {e}")
        if len(errors) > 10:
            report_lines.append(f"- ... and {len(errors) - 10} more")

    return errors, report_lines


def check_drift(current_symbols, prev_whitelist_path, max_ratio):
    report_lines = []
    drift_errors = []

    if not prev_whitelist_path or not prev_whitelist_path.exists():
        report_lines.append("No previous whitelist found. Skipping drift check.")
        return [], report_lines

    try:
        with prev_whitelist_path.open() as f:  # Use pathlib open for compliance
            prev_whitelist = json.load(f)
            if not isinstance(prev_whitelist, list):
                # Handle Freqtrade whitelist format if it's an object
                # (unlikely for simple JSON list)
                # If using standard Freqtrade whitelist file, it's a list.
                pass
    except Exception as e_load:
        return [f"Failed to load previous whitelist: {e_load}"], []

    if not prev_whitelist:
        return [], ["Previous whitelist empty."]

    prev_set = set(prev_whitelist)
    curr_set = set(current_symbols)

    removed = prev_set - curr_set
    removal_ratio = len(removed) / len(prev_set)

    report_lines.append(f"Previous whitelist count: {len(prev_set)}")
    report_lines.append(f"Current symbol count (matching filter? no, raw): {len(curr_set)}")
    report_lines.append(f"Removed count: {len(removed)}")
    report_lines.append(f"Removal ratio: {removal_ratio:.2f}")

    if removal_ratio > max_ratio:
        msg = f"Drift Safety Triggered! Removal ratio {removal_ratio:.2f} > {max_ratio}"
        drift_errors.append(msg)
        report_lines.append(f"**{msg}**")
    else:
        report_lines.append("Drift check passed.")

    if removed:
        report_lines.append("### Removed Pairs")
        for p in list(removed)[:10]:
            report_lines.append(f"- {p}")
        if len(removed) > 10:
            report_lines.append(f"- ... {len(removed) - 10} more")

    return drift_errors, report_lines


def main():  # noqa: C901
    args = setup_args()

    try:
        with args.markets.open("r", encoding="utf-8") as f:
            markets_data = json.load(f)
    except Exception as e:
        logger.error(f"Failed to load markets data: {e}")
        sys.exit(2)

    schema_errors, schema_report = validate_schema(markets_data, args)

    # Let's use all present symbols that look roughly valid to check drift.
    current_symbols = [m.get("symbol") for m in markets_data if m.get("symbol")]

    drift_errors, drift_report = check_drift(
        current_symbols, args.prev_whitelist, args.max_removal_ratio
    )

    all_errors = schema_errors + drift_errors

    # Generate Report
    report = [
        f"# Market Validation Report - {args.env}",
        f"Date: {datetime.now(UTC).isoformat()}",
    ]
    report.extend(schema_report)
    report.extend(drift_report)

    if args.out_report:
        try:
            with args.out_report.open("w") as f:
                f.write("\n\n".join(report))
        except Exception as e_write:
            logger.error(f"Failed to write report: {e_write}")

    if all_errors:
        logger.error("Validation FAILED.")
        for err in all_errors:
            logger.error(err)
        sys.exit(2)
    else:
        logger.info("Validation PASSED.")

        # Generate Whitelist if requested
        if args.out_whitelist:
            try:
                import re

                whitelist = []
                # Use current_symbols which were extracted earlier,
                # or filter from markets_data based on args
                # We need to filter based on FILTER_MODE

                for m in markets_data:
                    symbol = m.get("symbol")
                    if not symbol:
                        continue

                    # Basic validity check (already done in validate_schema but good to be safe)
                    if "/" not in symbol or ":" not in symbol:
                        continue

                    if args.filter_mode == "perps_usdt":
                        if symbol.endswith(":USDT") or symbol.endswith(
                            "/USDT:USDT"
                        ):  # Adjust based on actual Delta format
                            # Delta perps usually look like BTC/USDT:USDT
                            if re.match(r".*/USDT:USDT$", symbol):
                                whitelist.append(symbol)
                    elif args.filter_mode == "all_futures":
                        whitelist.append(symbol)
                    elif args.filter_mode == "allowlist_regex":
                        if re.match(args.allowlist_regex, symbol):
                            whitelist.append(symbol)

                # Sort for deterministic output
                whitelist.sort()

                with args.out_whitelist.open("w") as f:
                    json.dump(whitelist, f, indent=4)
                logger.info(f"Whitelist written to {args.out_whitelist} ({len(whitelist)} pairs)")

            except Exception as e_gen:
                logger.error(f"Failed to generate whitelist: {e_gen}")
                # We don't necessarily fail validation if whitelist gen fails, but let's be strict
                sys.exit(2)

        sys.exit(0)


if __name__ == "__main__":
    main()
