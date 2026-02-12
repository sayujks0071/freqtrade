#!/usr/bin/env python3
import json
import os
import re
import sys
from datetime import UTC, datetime
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
    # Assuming volume might be in 'info' or direct fields depending on exchange
    # Freqtrade dump usually standardizes some fields.
    if "volume" in m:
        vol = m.get("volume")
        if vol is not None and vol < 1000 and STRICT_VOLUME:
            errors.append(f"Low volume for {symbol}: {vol}")
    else:
        # Volume data often not in list-markets, only tickers
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

        validate_symbol_format(symbol, errors)

        # Uniqueness
        if symbol in symbols:
            errors.append(f"Duplicate symbol '{symbol}'")
        symbols.add(symbol)

        validate_volume(m, symbol, errors)

    if errors:
        fail(
            "Schema errors:\n"
            + "\n".join(errors[:10])
            + (f"\n...and {len(errors) - 10} more" if len(errors) > 10 else "")
        )

    return symbols


def validate_drift(current_symbols, previous_path):
    prev_path_obj = Path(previous_path)
    if not previous_path or not prev_path_obj.exists():
        print("No previous dump found. Skipping drift check.")
        return

    try:
        with prev_path_obj.open() as f:
            prev_data = json.load(f)
            # Handle if previous dump is also list of dicts or list of strings?
            # We enforce consistency.
            if isinstance(prev_data, list):
                if prev_data and isinstance(prev_data[0], dict):
                    prev_symbols = {m.get("symbol") for m in prev_data if "symbol" in m}
                elif prev_data and isinstance(prev_data[0], str):
                    prev_symbols = set(prev_data)
                else:
                    prev_symbols = set()  # Empty
            elif isinstance(prev_data, dict) and "markets" in prev_data:
                # Standard freqtrade dump
                prev_symbols = {m.get("symbol") for m in prev_data["markets"]}
            else:
                warn("Previous dump format unrecognized. Assuming empty.")
                prev_symbols = set()

    except Exception as e:
        warn(f"Could not read previous dump: {e}")
        return

    if not prev_symbols:
        return

    removed = prev_symbols - current_symbols
    added = current_symbols - prev_symbols

    removal_ratio = len(removed) / len(prev_symbols) if len(prev_symbols) > 0 else 0.0

    print(f"Drift stats: +{len(added)} / -{len(removed)} (Ratio: {removal_ratio:.2f})")

    if removal_ratio > MAX_REMOVAL_RATIO:
        fail(
            f"Removal ratio {removal_ratio:.2f} > MAX_REMOVAL_RATIO "
            f"({MAX_REMOVAL_RATIO}). Unsafe drift!"
        )


def write_report(path, message):
    with Path(path).open("w") as f:
        f.write(message)


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

    # Handle different potential inputs
    if isinstance(data, dict) and "markets" in data:
        data = data["markets"]
    elif isinstance(data, dict):
        # Maybe ccxt dict of dicts? Convert to list
        data = list(data.values())

    symbols = validate_schema(data)

    if prev_path:
        validate_drift(symbols, prev_path)

    report = f"""# Markets Schema Validation Report
Date: {datetime.now(UTC).isoformat()}
Status: PASS
Markets count: {len(symbols)}
File: {current_path}
"""

    # Write report if needed, usually we rely on stdout for simple CI checks but saving is good
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    report_file = f"user_data/reports/markets_schema_report_{ts}.md"
    try:
        # Create dir if not exists (script should handle it but safe to check)
        Path("user_data/reports").mkdir(parents=True, exist_ok=True)
        write_report(report_file, report)
        print(f"Report written to {report_file}")
    except Exception as e:
        warn(f"Could not write report: {e}")

    print("VALIDATION PASS")


if __name__ == "__main__":
    main()
