#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# Configuration defaults
DEFAULT_MIN_MARKETS = 20
DEFAULT_MAX_REMOVAL_RATIO = 0.25
DEFAULT_STRICT_VOLUME = False

REQUIRED_FIELDS = ["symbol", "base", "quote", "active"]

def fail(message):
    print(f"FAIL: {message}")
    sys.exit(2)

def warn(message):
    print(f"WARN: {message}")

def get_env_bool(name, default):
    val = os.environ.get(name, str(default)).lower()
    return val in ("true", "1", "yes", "on")

def validate_market_structure(i, m, errors):
    # Check required fields
    for f in REQUIRED_FIELDS:
        if f not in m:
            errors.append(f"Item {i} missing field '{f}'")

    symbol = m.get("symbol", "")
    if not symbol:
        errors.append(f"Item {i} has empty symbol")
        return None
    return symbol

def validate_symbol_format(symbol, errors):
    # Symbol format: BASE/QUOTE:SETTLE for futures
    if re.search(r"\s", symbol):
        errors.append(f"Symbol '{symbol}' contains whitespace")
    if symbol != symbol.upper():
        errors.append(f"Symbol '{symbol}' is not uppercase")

    # Strict check for futures format (must have settle currency delimiter)
    # The prompt specifies: "symbol format consistency; reject ... missing settle delimiter in futures mode"
    if ":" not in symbol:
        errors.append(f"Symbol '{symbol}' missing settle delimiter (:). Expected BASE/QUOTE:SETTLE")

def validate_volume(m, symbol, strict_volume, errors):
    # Volume check if available and strict mode is on
    if strict_volume and "volume" in m:
        vol = m.get("volume")
        if isinstance(vol, (int, float)) and vol < 1000:
            errors.append(f"Low volume for {symbol}: {vol}")

def validate_schema(data, min_markets, strict_volume):
    if not isinstance(data, list):
        fail("Root must be a list of markets")

    if len(data) < min_markets:
        fail(f"Market count {len(data)} < MIN_MARKETS ({min_markets})")

    symbols = set()
    errors = []

    for i, m in enumerate(data):
        symbol = validate_market_structure(i, m, errors)
        if not symbol:
            continue

        validate_symbol_format(symbol, errors)

        # Uniqueness
        if symbol in symbols:
            errors.append(f"Duplicate symbol '{symbol}'")
        symbols.add(symbol)

        validate_volume(m, symbol, strict_volume, errors)

    if errors:
        fail(
            "Schema errors:\n"
            + "\n".join(errors[:10])
            + (f"\n...and {len(errors) - 10} more" if len(errors) > 10 else "")
        )

    return symbols

def validate_drift(current_symbols, previous_path, max_removal_ratio):
    prev_path_obj = Path(previous_path)
    if not previous_path or not prev_path_obj.exists():
        print("No previous dump found. Skipping drift check.")
        return

    try:
        with prev_path_obj.open() as f:
            prev_data = json.load(f)
            # Support both raw list and dict wrapper
            if isinstance(prev_data, dict) and "markets" in prev_data:
                prev_data = prev_data["markets"]

            prev_symbols = {m["symbol"] for m in prev_data if isinstance(m, dict) and "symbol" in m}
    except Exception as e:
        warn(f"Could not read previous dump for drift check: {e}")
        return

    removed = prev_symbols - current_symbols
    added = current_symbols - prev_symbols

    count_prev = len(prev_symbols)
    removal_ratio = len(removed) / count_prev if count_prev > 0 else 0.0

    print(f"Drift stats: +{len(added)} / -{len(removed)} (Ratio: {removal_ratio:.2f})")

    if removed:
        print("Removed pairs sample:", list(removed)[:5])

    if removal_ratio > max_removal_ratio:
        fail(
            f"Removal ratio {removal_ratio:.2f} > MAX_REMOVAL_RATIO "
            f"({max_removal_ratio}). Unsafe drift! Check if API format changed."
        )

def write_report(path, message):
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w") as f:
            f.write(message)
        print(f"Report written to {path}")
    except Exception as e:
        warn(f"Could not write report: {e}")

def main():
    parser = argparse.ArgumentParser(description="Validate Markets Schema and Drift")
    parser.add_argument("current", help="Path to current markets JSON")
    parser.add_argument("previous", nargs="?", help="Path to previous markets JSON for drift check")

    args = parser.parse_args()

    # Load config from Env
    min_markets = int(os.environ.get("MIN_MARKETS", DEFAULT_MIN_MARKETS))
    max_removal_ratio = float(os.environ.get("MAX_REMOVAL_RATIO", DEFAULT_MAX_REMOVAL_RATIO))
    strict_volume = get_env_bool("STRICT_VOLUME", DEFAULT_STRICT_VOLUME)

    print(f"Validating {args.current}...")
    print(f"Config: MIN_MARKETS={min_markets}, MAX_REMOVAL_RATIO={max_removal_ratio}, STRICT_VOLUME={strict_volume}")

    try:
        with Path(args.current).open() as f:
            data = json.load(f)
    except Exception as e:
        fail(f"Invalid JSON in {args.current}: {e}")

    if isinstance(data, dict) and "markets" in data:
        data = data["markets"]

    symbols = validate_schema(data, min_markets, strict_volume)

    if args.previous:
        validate_drift(symbols, args.previous, max_removal_ratio)

    # Generate Report
    ts = datetime.now(timezone.utc).isoformat()
    report = f"""# Markets Schema Validation Report
Date: {ts}
Status: PASS
Markets count: {len(symbols)}
File: {args.current}
Previous File: {args.previous or 'N/A'}
"""

    report_filename = f"user_data/reports/markets_schema_report_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.md"
    write_report(report_filename, report)

    print("VALIDATION PASS")

if __name__ == "__main__":
    main()
