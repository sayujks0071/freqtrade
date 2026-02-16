#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


# Config
MIN_MARKETS = int(os.environ.get("MIN_MARKETS", 20))
MAX_REMOVAL_RATIO = float(os.environ.get("MAX_REMOVAL_RATIO", 0.25))
STRICT_VOLUME = os.environ.get("STRICT_VOLUME", "false").lower() == "true"
FILTER_MODE = os.environ.get("FILTER_MODE", "perps_usdt")
ALLOWLIST_REGEX = os.environ.get("ALLOWLIST_REGEX", ".*")


def is_eligible(market):
    """
    Determines if a market is eligible for the whitelist based on FILTER_MODE.
    """
    symbol = market.get("symbol", "")
    if not market.get("active"):
        return False

    # Basic Futures check (CCXT structure)
    if not (market.get("linear") or market.get("contract")):
        return False

    # Symbol format check: BASE/QUOTE:SETTLE
    if ":" not in symbol:
        return False

    if FILTER_MODE == "perps_usdt":
        return (
            market.get("quote") == "USDT"
            and market.get("settle") == "USDT"
            and market.get("contract") is True
        )
    elif FILTER_MODE == "all_futures":
        return market.get("contract") is True
    elif FILTER_MODE == "allowlist_regex":
        return re.match(ALLOWLIST_REGEX, symbol) is not None

    return False


def load_markets(markets_path):
    try:
        with Path(markets_path).open("r") as f:
            return json.load(f)
    except Exception as e:
        print(f"ERROR: Could not read markets file: {e}")
        sys.exit(2)


def check_drift(prev_whitelist_path, current_pairs, report_lines, errors, warnings):
    if not prev_whitelist_path or not Path(prev_whitelist_path).exists():
        report_lines.append("- No previous whitelist found (First Run)")
        return

    try:
        with Path(prev_whitelist_path).open("r") as f:
            prev_data = json.load(f)

        prev_pairs = set()
        if isinstance(prev_data, dict) and "exchange" in prev_data:
            prev_pairs = set(prev_data["exchange"].get("pair_whitelist", []))
        elif isinstance(prev_data, list):
            prev_pairs = set(prev_data)

        removed = prev_pairs - current_pairs
        added = current_pairs - prev_pairs

        removal_ratio = len(removed) / len(prev_pairs) if len(prev_pairs) > 0 else 0.0

        report_lines.append(f"- Previous Whitelist Size: {len(prev_pairs)}")
        report_lines.append(f"- Removed Pairs: {len(removed)} ({removal_ratio:.2%})")
        report_lines.append(f"- Added Pairs: {len(added)}")

        if removal_ratio > MAX_REMOVAL_RATIO:
            errors.append(
                f"Removal ratio {removal_ratio:.2%} > MAX_REMOVAL_RATIO {MAX_REMOVAL_RATIO:.2%}"
            )
            report_lines.append("  - BLOCKED: Too many removals!")

    except Exception as e:
        warnings.append(f"Could not read previous whitelist: {e}")


def filter_markets(markets, report_lines):
    errors = []
    eligible_markets = []
    seen_symbols = set()

    for m in markets:
        symbol = m.get("symbol")
        if not symbol:
            continue  # skip malformed

        if is_eligible(m):
            if symbol.lower() in seen_symbols:
                errors.append(f"Duplicate symbol found: {symbol}")
            seen_symbols.add(symbol.lower())

            # Strict format check
            if not re.match(r"^[A-Z0-9]+/[A-Z0-9]+:[A-Z0-9]+$", symbol):
                errors.append(f"Invalid symbol format: {symbol}")

            eligible_markets.append(symbol)

    report_lines.append(f"- Eligible Markets: {len(eligible_markets)}")
    return eligible_markets, errors


def validate(markets_path, prev_whitelist_path, report_path):
    report_lines = [f"# Market Validation Report ({datetime.now(timezone.utc).isoformat()})"]
    errors = []
    warnings = []

    markets = load_markets(markets_path)

    if not isinstance(markets, list):
        errors.append("Markets dump is not a list.")
        sys.exit(2)

    total_markets = len(markets)
    report_lines.append(f"- Total Markets in Dump: {total_markets}")

    if total_markets < MIN_MARKETS:
        errors.append(f"Total markets ({total_markets}) < MIN_MARKETS ({MIN_MARKETS})")

    eligible_markets, market_errors = filter_markets(markets, report_lines)
    errors.extend(market_errors)

    # Drift Check
    check_drift(prev_whitelist_path, set(eligible_markets), report_lines, errors, warnings)

    # Output Report
    report_lines.append("\n## Errors")
    if errors:
        for e in errors:
            report_lines.append(f"- 🔴 {e}")
    else:
        report_lines.append("- None")

    report_lines.append("\n## Warnings")
    if warnings:
        for w in warnings:
            report_lines.append(f"- ⚠️ {w}")
    else:
        report_lines.append("- None")

    with Path(report_path).open("w") as f:
        f.write("\n".join(report_lines))

    if errors:
        print("Validation FAILED. See report.")
        sys.exit(2)
    else:
        print("Validation PASSED.")
        sys.exit(0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--markets", required=True)
    parser.add_argument("--prev-whitelist", required=False)
    parser.add_argument("--env", required=False)
    parser.add_argument("--out-report", required=True)
    args = parser.parse_args()

    validate(args.markets, args.prev_whitelist, args.out_report)
