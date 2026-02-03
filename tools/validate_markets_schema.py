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
DELTA_ENV = os.environ.get("DELTA_ENV", "global_prod")

REQUIRED_FIELDS = ["symbol", "base", "quote", "active"]

# Sanity check for env
EXPECTED_URL_PART = "testnet" if "testnet" in DELTA_ENV else "delta.exchange"


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
        # Ensure vol is a number
        try:
            vol = float(vol) if vol is not None else 0.0
            if vol < 1000 and STRICT_VOLUME:
                errors.append(f"Low volume for {symbol}: {vol}")
            if vol < 0:
                errors.append(f"Negative volume for {symbol}: {vol}")
        except ValueError:
            pass  # Ignore if not convertible

    # Check limits
    if "limits" in m:
        limits = m.get("limits", {})
        for k, v in limits.items():
            if isinstance(v, dict):
                if v.get("min") is not None and v["min"] < 0:
                    errors.append(f"Negative min limit for {symbol} {k}: {v['min']}")


def validate_schema(data):
    if not isinstance(data, list):
        # Maybe it's a dict with 'markets' key?
        if isinstance(data, dict) and "markets" in data:
            data = data["markets"]
        else:
            fail("Root must be a list of markets or dict with 'markets' key")

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
    if not previous_path:
        print("No previous dump provided. Skipping drift check.")
        return

    prev_path_obj = Path(previous_path)
    if not prev_path_obj.exists():
        print(f"Previous dump {previous_path} does not exist. Skipping drift check.")
        return

    try:
        with prev_path_obj.open() as f:
            prev_data = json.load(f)
            # Handle if previous dump is also list of dicts
            if isinstance(prev_data, dict) and "markets" in prev_data:
                prev_data = prev_data["markets"]

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
    try:
        with Path(path).open("w") as f:
            f.write(message)
    except Exception as e:
        warn(f"Could not write report: {e}")


def main():
    if len(sys.argv) < 2:
        print(
            "Usage: validate_markets_schema.py <current_json> [previous_json] [report_out]"
        )
        sys.exit(1)

    current_path = sys.argv[1]
    prev_path = sys.argv[2] if len(sys.argv) > 2 else None
    report_path = sys.argv[3] if len(sys.argv) > 3 else None

    print(f"Validating {current_path}...")

    # Safe Load
    try:
        with Path(current_path).open() as f:
            raw_data = json.load(f)
    except Exception as e:
        fail(f"Invalid JSON: {e}")

    data = raw_data
    if isinstance(raw_data, dict) and "markets" in raw_data:
        data = raw_data["markets"]

    symbols = validate_schema(data)

    if prev_path:
        validate_drift(symbols, prev_path)

    # Sanity check env url in info if possible (hard to do without info field)
    # But we can check if data looks real.

    report = f"""# Markets Schema Validation Report
Date: {datetime.now(timezone.utc).isoformat()}
Status: PASS
Markets count: {len(symbols)}
File: {current_path}
"""

    if report_path:
        write_report(report_path, report)
        print(f"Report written to {report_path}")
    else:
        # Default fallback
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        write_report(f"user_data/reports/markets_schema_report_{ts}.md", report)

    print("VALIDATION PASS")


if __name__ == "__main__":
    main()
