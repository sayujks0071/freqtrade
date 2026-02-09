#!/usr/bin/env python3
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# Configuration
MIN_MARKETS = int(os.environ.get("MIN_MARKETS", 20))
MAX_REMOVAL_RATIO = float(os.environ.get("MAX_REMOVAL_RATIO", 0.25))
STRICT_VOLUME = os.environ.get("STRICT_VOLUME", "false").lower() == "true"

REQUIRED_FIELDS = ["symbol", "base", "quote", "active"]


def fail(message):
    print(f"FAIL: {message}")
    sys.exit(2)


def warn(message):
    print(f"WARN: {message}")


def validate_market_structure(i, m, errors):
    # Required fields
    for f in REQUIRED_FIELDS:
        if f not in m:
            errors.append(f"Item {i} missing field '{f}'")

    symbol = m.get("symbol", "")
    if not symbol:
        errors.append(f"Item {i} has empty symbol")
        return None
    return symbol


def validate_symbol_format(symbol, errors):
    # Symbol format: BASE/QUOTE:SETTLE for futures usually
    # Reject whitespace/lowercase
    if re.search(r"\s", symbol):
        errors.append(f"Symbol '{symbol}' contains whitespace")
    if symbol != symbol.upper():
        errors.append(f"Symbol '{symbol}' is not uppercase")
    # Strict check for futures format (must have settle currency)
    if ":" not in symbol:
        errors.append(f"Symbol '{symbol}' missing settle delimiter (:)")


def validate_volume(m, symbol, errors):
    # Volume check (if strict)
    if "info" in m and isinstance(m["info"], dict):
        # Delta exchange specific structure often in 'info'
        # But list-markets usually just has basic info
        pass


def validate_schema(data):
    if not isinstance(data, list):
        fail("Root must be a list of markets")

    if len(data) < MIN_MARKETS:
        fail(f"Market count {len(data)} < MIN_MARKETS ({MIN_MARKETS})")

    symbols = set()
    errors = []

    for i, m in enumerate(data):
        symbol = validate_market_structure(i, m, errors)
        if not symbol:
            continue

        # Only validate format for what looks like a pair
        # Sometimes list-markets returns oddities, but we enforce strictness for our usage
        validate_symbol_format(symbol, errors)

        # Uniqueness
        if symbol in symbols:
            errors.append(f"Duplicate symbol '{symbol}'")
        symbols.add(symbol)

        validate_volume(m, symbol, errors)

    if errors:
        # Print top 10 errors
        print("Schema errors:")
        for e in errors[:10]:
            print(f" - {e}")
        if len(errors) > 10:
            print(f" ...and {len(errors) - 10} more")
        fail("Schema validation failed")

    return symbols


def validate_drift(current_symbols, previous_path):
    prev_path_obj = Path(previous_path)
    if not previous_path or not prev_path_obj.exists():
        print("No previous dump found. Skipping drift check.")
        return

    try:
        with prev_path_obj.open() as f:
            prev_data = json.load(f)

        # Normalize structure
        if isinstance(prev_data, dict) and "markets" in prev_data:
            prev_data = prev_data["markets"]

        if not isinstance(prev_data, list):
             warn(f"Previous dump invalid format. Skipping drift.")
             return

        prev_symbols = set()
        for m in prev_data:
            if "symbol" in m:
                prev_symbols.add(m["symbol"])

    except Exception as e:
        warn(f"Could not read previous dump: {e}")
        return

    if not prev_symbols:
        return

    removed = prev_symbols - current_symbols
    added = current_symbols - prev_symbols

    removal_ratio = len(removed) / len(prev_symbols)

    print(f"Drift stats: +{len(added)} / -{len(removed)} (Ratio: {removal_ratio:.2f})")

    if removal_ratio > MAX_REMOVAL_RATIO:
        fail(
            f"Removal ratio {removal_ratio:.2f} > MAX_REMOVAL_RATIO "
            f"({MAX_REMOVAL_RATIO}). Unsafe drift!"
        )


def write_report(path, message):
    try:
        with Path(path).open("w") as f:
            f.write(message)
    except Exception as e:
        warn(f"Could not write report: {e}")


def main():
    if len(sys.argv) < 2:
        print("Usage: validate_markets_schema.py <current_json> [previous_json]")
        sys.exit(1)

    current_path = sys.argv[1]
    prev_path = sys.argv[2] if len(sys.argv) > 2 else None

    print(f"Validating {current_path}...")

    try:
        with Path(current_path).open() as f:
            data = json.load(f)
    except Exception as e:
        fail(f"Invalid JSON: {e}")

    # Standardize input
    if isinstance(data, dict) and "markets" in data:
        data = data["markets"]

    # Sometimes list-markets might return just a list of strings (if simple output used), but we expect objects
    # If using --print-json with freqtrade list-markets, it usually returns a list of objects or dict with 'markets' list of objects.

    symbols = validate_schema(data)

    if prev_path:
        validate_drift(symbols, prev_path)

    report = f"""# Markets Schema Validation Report
Date: {datetime.now(timezone.utc).isoformat()}
Status: PASS
Markets count: {len(symbols)}
File: {current_path}
"""

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    report_file = f"user_data/reports/markets_schema_report_{ts}.md"
    write_report(report_file, report)
    print(f"Report written to {report_file}")
    print("VALIDATION PASS")


if __name__ == "__main__":
    main()
