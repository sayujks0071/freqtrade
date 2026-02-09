#!/usr/bin/env python3
"""
Validates the markets dump from Freqtrade against schema and sanity checks.
Ensures critical data integrity before allowing whitelist updates.
"""

import argparse
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path


# Configuration (Defaults can be overridden by env vars)
MIN_MARKETS = int(os.environ.get("MIN_MARKETS", 20))
STRICT_VOLUME = os.environ.get("STRICT_VOLUME", "false").lower() == "true"
DELTA_ENV = os.environ.get("DELTA_ENV", "india_prod")
MAX_REMOVAL_RATIO = float(os.environ.get("MAX_REMOVAL_RATIO", 0.25))

# Whitelist generation settings
FILTER_MODE = os.environ.get("FILTER_MODE", "perps_usdt")
ALLOWLIST_REGEX = os.environ.get("ALLOWLIST_REGEX", ".*")

REQUIRED_FIELDS = ["symbol", "base", "quote", "active"]


def parse_args():
    parser = argparse.ArgumentParser(description="Validate markets schema and sanity.")
    parser.add_argument("--markets", required=True, help="Path to markets JSON file")
    parser.add_argument("--env", default=DELTA_ENV, help="Expected DELTA_ENV (e.g., india_prod)")
    parser.add_argument("--prev-whitelist", help="Path to previous whitelist JSON for drift check")
    parser.add_argument(
        "--out-report", help="Path to write Markdown report", default="validation_report.md"
    )
    return parser.parse_args()


def fail(message, report_path=None, report_content=None):
    """Exit with error status."""
    print(f"FAIL: {message}")
    if report_path and report_content:
        write_report(report_path, report_content + f"\n\n**FAILURE REASON:** {message}")
    sys.exit(2)


def warn(message):
    print(f"WARN: {message}")


def write_report(path, content):
    try:
        with Path(path).open("w") as f:
            f.write(content)
        print(f"Report written to {path}")
    except Exception as e:
        print(f"ERROR: Could not write report to {path}: {e}")


def validate_market_structure(i, m, errors):
    """Validate individual market entry structure."""
    # Check required fields
    for f in REQUIRED_FIELDS:
        if f not in m:
            errors.append(f"Item {i} missing field '{f}'")

    symbol = m.get("symbol", "")
    if not symbol:
        errors.append(f"Item {i} has empty symbol")
        return None

    # Check for type/contract/future
    # Freqtrade/CCXT usually has 'type', 'future', 'spot', 'swap', 'contract'
    is_contract = (
        m.get("contract") is True
        or m.get("future") is True
        or m.get("swap") is True
        or m.get("type") in ("swap", "future")
    )

    if not is_contract and m.get("type") != "spot":
        # If not explicitly spot or contract, warn or fail?
        # For Delta, we mostly care about perps/futures.
        pass

    return symbol


def validate_symbol_format(symbol, errors):
    """Validate symbol format requirements."""
    # Symbol format: BASE/QUOTE:SETTLE for futures usually
    # Reject whitespace
    if re.search(r"\s", symbol):
        errors.append(f"Symbol '{symbol}' contains whitespace")

    # Reject lowercase (unless some exchange uses it, but standard is UPPER)
    if symbol != symbol.upper():
        errors.append(f"Symbol '{symbol}' is not uppercase")

    # Strict check for futures format (must have settle currency if it's a future)
    # This might be too strict for spot, but Delta is mostly derivatives.
    # We'll check if it looks like a standard pair.
    if "/" not in symbol:
        errors.append(f"Symbol '{symbol}' missing base/quote delimiter (/)")


def validate_volume(m, symbol, errors):
    """Validate volume and other numeric fields."""
    # Volume check (if strict)
    # Freqtrade dump often puts volume in 'info' or top level if standardized.
    # We check 'volume' key if present.

    vol = m.get("volume")  # 24h volume
    if vol is not None:
        if not isinstance(vol, (int, float)):
            errors.append(f"Symbol '{symbol}' volume is not numeric: {vol}")
        elif vol < 0:
            errors.append(f"Symbol '{symbol}' has negative volume: {vol}")
        elif STRICT_VOLUME and vol < 1000:  # Arbitrary threshold for "liquid"
            # Just a warning unless STRICT_VOLUME is enforced elsewhere or here?
            # The prompt says: "allow STRICT_VOLUME=true to fail if too many are illiquid"
            # For now, we'll just log it as an error if strict.
            errors.append(f"Low volume for {symbol}: {vol}")


def check_environment_sanity(data, expected_env, errors):
    """
    Check if the dump corresponds to the intended DELTA_ENV.
    This is heuristic-based since 'exchange_id' isn't standard in list-markets output usually.
    But we can look at 'info' if present, or infer from symbol types or counts.
    """
    is_testnet = "testnet" in expected_env

    # Heuristic: Look for 'TEST' in symbols if PROD
    # This is weak but better than nothing.
    test_symbols_found = 0
    for m in data:
        sym = m.get("symbol", "")
        if "TEST" in sym:
            test_symbols_found += 1

    if not is_testnet and test_symbols_found > 0:
        warn(
            f"Found {test_symbols_found} 'TEST' symbols in PROD env {expected_env}. "
            "This might be normal for some delisted pairs, but implies caution."
        )
        # We don't fail here because sometimes TEST tokens exist in prod
        # (e.g. mock trading contests)
        # But if ALL are TEST, that's bad.
        if test_symbols_found == len(data):
            errors.append(f"All symbols appear to be TEST symbols in PROD env {expected_env}")


def generate_whitelist_candidates(markets):
    """
    Replicates logic from generate_whitelist.py to determine eligible pairs.
    """
    whitelist = []
    regex = re.compile(ALLOWLIST_REGEX)

    for m in markets:
        symbol = m.get("symbol")
        if not symbol:
            continue

        # Basic active check
        if not m.get("active", True):
            continue

        # Filter logic
        if FILTER_MODE == "perps_usdt":
            if "/USDT:USDT" in symbol:
                whitelist.append(symbol)
        elif FILTER_MODE == "all_futures":
            # Assuming all in dump are relevant or just check for futures structure
            whitelist.append(symbol)
        elif FILTER_MODE == "allowlist_regex":
            if regex.match(symbol):
                whitelist.append(symbol)
        else:
            # Default to perps_usdt
            if "/USDT:USDT" in symbol:
                whitelist.append(symbol)

    return sorted(list(set(whitelist)))


def validate_drift(current_markets, prev_whitelist_path, report_lines):
    """
    Compare current whitelist candidates against previous whitelist.
    """
    # 1. Generate current whitelist from markets dump
    current_whitelist = generate_whitelist_candidates(current_markets)
    report_lines.append(f"Eligible whitelist size: {len(current_whitelist)}")

    if not prev_whitelist_path or not Path(prev_whitelist_path).exists():
        report_lines.append("No previous whitelist found. Skipping drift check.")
        # Return success but empty errors
        return True, []

    # 2. Load previous whitelist
    prev_whitelist = []
    error_msg = None
    try:
        with Path(prev_whitelist_path).open() as f:
            prev_data = json.load(f)

        # Standard freqtrade whitelist format: {"exchange": {"pair_whitelist": [...]}}
        # Or simple list if custom
        if (
            isinstance(prev_data, dict)
            and "exchange" in prev_data
            and "pair_whitelist" in prev_data["exchange"]
        ):
            prev_whitelist = prev_data["exchange"]["pair_whitelist"]
        elif isinstance(prev_data, list):
            prev_whitelist = prev_data
        else:
            warn("Previous whitelist format unrecognized. Skipping drift check.")
            return True, []

    except Exception as exc:
        error_msg = f"Failed to read previous whitelist: {exc}"

    if error_msg:
        warn(error_msg)
        return True, []

    # 3. Compare
    prev_set = set(prev_whitelist)
    curr_set = set(current_whitelist)

    removed = prev_set - curr_set
    added = curr_set - prev_set

    removal_count = len(removed)
    prev_count = len(prev_set)

    removal_ratio = removal_count / prev_count if prev_count > 0 else 0.0

    report_lines.append("Drift Stats:")
    report_lines.append(f"- Previous: {prev_count}")
    report_lines.append(f"- Current: {len(curr_set)}")
    report_lines.append(f"- Added: {len(added)}")
    report_lines.append(f"- Removed: {removal_count}")
    report_lines.append(f"- Removal Ratio: {removal_ratio:.2%}")

    errors = []
    if removal_ratio > MAX_REMOVAL_RATIO:
        errors.append(
            f"Large delist drift: {removal_ratio:.2%} > {MAX_REMOVAL_RATIO:.0%} "
            f"(Limit: {MAX_REMOVAL_RATIO})"
        )
        report_lines.append("**DRIFT CHECK FAILED**")

    # Check for pair format changes (Heuristic: if high removal but high addition, might be rename)
    # If removal ratio is high, we already fail.

    return (len(errors) == 0), errors


def validate_schema(data, args):
    """Main schema validation logic."""
    report_lines = []

    if not isinstance(data, list):
        return False, ["Root must be a list of markets"], [], set()

    market_count = len(data)
    report_lines.append(f"Total markets found: {market_count}")

    if market_count < MIN_MARKETS:
        return (
            False,
            [f"Market count {market_count} < MIN_MARKETS ({MIN_MARKETS})"],
            report_lines,
            set(),
        )

    symbols = set()
    errors = []

    check_environment_sanity(data, args.env, errors)

    # Validation Loop
    for i, m in enumerate(data):
        symbol = validate_market_structure(i, m, errors)
        if not symbol:
            continue

        validate_symbol_format(symbol, errors)

        # Uniqueness
        if symbol in symbols:
            errors.append(f"Duplicate symbol '{symbol}'")
        symbols.add(symbol)

        validate_volume(m, symbol, errors)

    return (len(errors) == 0), errors, report_lines, symbols


def main():
    args = parse_args()

    print(f"Validating {args.markets} against env {args.env}...")

    # 1. Load Data
    try:
        with Path(args.markets).open() as f:
            data = json.load(f)
    except Exception as e:
        fail(f"Invalid JSON in {args.markets}: {e}")

    if isinstance(data, dict) and "markets" in data:
        data = data["markets"]

    # 2. Validate Schema
    success_schema, schema_errors, report_lines, _symbols = validate_schema(data, args)

    drift_errors = []
    if success_schema:
        # 3. Drift Check
        success_drift, drift_errors = validate_drift(data, args.prev_whitelist, report_lines)
    else:
        success_drift = False
        report_lines.append("Skipping drift check due to schema errors.")

    # Prepare Report
    success = success_schema and success_drift

    report_header = f"""# Markets Schema Validation Report
Date: {datetime.now(UTC).isoformat()}
File: {args.markets}
Environment: {args.env}
Status: {"PASS" if success else "FAIL"}
"""

    full_report = report_header + "\n".join(report_lines) + "\n\n"

    all_errors = schema_errors + drift_errors
    if all_errors:
        full_report += "## Errors\n"
        for err in all_errors:
            full_report += f"- {err}\n"

    write_report(args.out_report, full_report)

    if not success:
        print("Validation FAILED. See report.")
        sys.exit(2)

    print("Validation PASSED.")
    sys.exit(0)


if __name__ == "__main__":
    main()
