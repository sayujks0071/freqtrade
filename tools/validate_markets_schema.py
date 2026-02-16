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
            # Handle if previous dump is also list of dicts
            prev_symbols = {m["symbol"] for m in prev_data if "symbol" in m}
    except Exception as e:
        warn(f"Could not read previous dump: {e}")
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


def validate_whitelist(config_path, market_symbols):
    if not config_path:
        return

    print(f"Validating whitelist from {config_path}...")
    try:
        with Path(config_path).open() as f:
            config = json.load(f)
    except Exception as e:
        fail(f"Could not read config file: {e}")

    whitelist = config.get("exchange", {}).get("pair_whitelist", [])
    if not whitelist:
        warn("Whitelist is empty in config.")
        return

    missing = []
    # Freqtrade list-markets returns symbols in Base/Quote:Settle format (for futures)
    # or just Base/Quote (spot).
    # We should normalize/check exactly.
    for pair in whitelist:
        if pair not in market_symbols:
            missing.append(pair)

    if missing:
        fail(f"Whitelist pairs missing in markets dump: {missing}")

    print(f"Whitelist validation PASS: All {len(whitelist)} pairs found in markets dump.")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Validate markets schema and whitelist.")
    parser.add_argument("markets", help="Path to markets JSON file")
    parser.add_argument(
        "--prev-whitelist", help="Path to previous whitelist/markets for drift check"
    )
    parser.add_argument("--config", help="Path to config file to validate whitelist")

    args = parser.parse_args()

    current_path = args.markets
    prev_path = args.prev_whitelist
    config_path = args.config

    print(f"Validating {current_path}...")

    try:
        with Path(current_path).open() as f:
            data = json.load(f)
    except Exception as e:
        fail(f"Invalid JSON: {e}")

    # Depending on freqtrade version, list-markets might output a dict with "markets" key
    # or just a list. The prompt implies "list-markets futures json dump".
    if isinstance(data, dict) and "markets" in data:
        data = data["markets"]

    symbols = validate_schema(data)

    if prev_path:
        validate_drift(symbols, prev_path)

    if config_path:
        validate_whitelist(config_path, symbols)

    report = f"""# Markets Schema Validation Report
Date: {datetime.now(UTC).isoformat()}
Status: PASS
Markets count: {len(symbols)}
File: {current_path}
"""
    # We could write this report to a file if needed, but stdout is fine for now
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    report_file = f"user_data/reports/markets_schema_report_{ts}.md"
    try:
        write_report(report_file, report)
        print(f"Report written to {report_file}")
    except Exception as e:
        warn(f"Could not write report: {e}")

    print("VALIDATION PASS")


if __name__ == "__main__":
    main()
