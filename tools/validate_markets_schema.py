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
    # Symbol format: BASE/QUOTE:SETTLE for futures
    # Strict Regex
    # Matches: BTC/USDT:USDT, ETH/BTC:BTC, etc.
    # Allows alphanumeric + some special chars if needed, but standard is alphanumeric
    pattern = r"^[A-Z0-9]+/[A-Z0-9]+:[A-Z0-9]+$"

    if not re.match(pattern, symbol):
        errors.append(f"Symbol '{symbol}' does not match futures format BASE/QUOTE:SETTLE")
        return

    if re.search(r"\s", symbol):
        errors.append(f"Symbol '{symbol}' contains whitespace")
    if symbol != symbol.upper():
        errors.append(f"Symbol '{symbol}' is not uppercase")


def validate_volume(m, symbol, errors):
    # Volume check (if strict)
    # Assuming volume might be in 'info' or direct fields depending on exchange
    # Freqtrade dump usually standardizes some fields.
    # But Freqtrade 'list-markets' dump primarily contains metadata, not necessarily 24h volume.
    # If volume is present, we check it.

    vol = m.get("quoteVolume") or m.get("baseVolume")  # Freqtrade/CCXT standard

    # If not at top level, check info
    if vol is None and "info" in m:
        # Delta specific: '24h_volume' or similar in info
        pass

    if vol is not None and vol < 1000 and STRICT_VOLUME:
        errors.append(f"Low volume for {symbol}: {vol}")


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
            + "\n".join(errors[:20])
            + (f"\n...and {len(errors) - 20} more" if len(errors) > 20 else "")
        )

    return symbols


def validate_drift(current_symbols, previous_path):  # noqa: C901, RUF100
    prev_path_obj = Path(previous_path)
    if not previous_path or not prev_path_obj.exists():
        print("No previous dump found. Skipping drift check.")
        return

    try:
        with prev_path_obj.open() as f:
            prev_data = json.load(f)
            # Handle if previous dump is list of dicts
            prev_symbols = set()
            if isinstance(prev_data, list):
                for m in prev_data:
                    if isinstance(m, dict):
                        prev_symbols.add(m.get("symbol"))
                    elif isinstance(m, str):
                        prev_symbols.add(m)
            elif isinstance(prev_data, dict) and "markets" in prev_data:
                for m in prev_data["markets"]:
                    if isinstance(m, dict):
                        prev_symbols.add(m.get("symbol"))

    except Exception as e:
        warn(f"Could not read previous dump: {e}")
        return

    if not prev_symbols:
        warn("Previous dump contained no symbols.")
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

    # Standardize data
    if isinstance(data, dict):
        if "markets" in data:
            data = data["markets"]
        elif "pairs" in data:
            data = data["pairs"]

    symbols = validate_schema(data)

    if prev_path:
        validate_drift(symbols, prev_path)

    report = f"""# Markets Schema Validation Report
Date: {datetime.now(UTC).isoformat()}
Status: PASS
Markets count: {len(symbols)}
File: {current_path}
"""
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    report_file = f"user_data/reports/markets_schema_report_{ts}.md"
    try:
        Path("user_data/reports").mkdir(parents=True, exist_ok=True)
        write_report(report_file, report)
        print(f"Report written to {report_file}")
    except Exception as e:
        warn(f"Could not write report: {e}")

    print("VALIDATION PASS")


if __name__ == "__main__":
    main()
