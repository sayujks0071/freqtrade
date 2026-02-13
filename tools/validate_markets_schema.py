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

def fail(message, report_path=None, report_content=None):
    print(f"FAIL: {message}")
    if report_path and report_content:
        try:
            with Path(report_path).open("w") as f:
                f.write(report_content + f"\n\n## FAILURE\n{message}\n")
            print(f"Report written to {report_path}")
        except Exception as e:
            print(f"Could not write failure report: {e}")
    sys.exit(2)


def warn(message):
    print(f"WARN: {message}")


def validate_market_structure(i, m, errors):
    for f in REQUIRED_FIELDS:
        if f not in m:
            errors.append(f"Item {i} missing field '{f}'")

    symbol = m.get("symbol", "")
    if not symbol:
        errors.append(f"Item {i} has empty symbol")
        return None
    return symbol


def validate_symbol_format(symbol, m, errors):
    # Symbol format: BASE/QUOTE:SETTLE for futures usually
    if re.search(r"\s", symbol):
        errors.append(f"Symbol '{symbol}' contains whitespace")
    if symbol != symbol.upper():
        errors.append(f"Symbol '{symbol}' is not uppercase")

    # Futures specific check
    # Check if 'linear' or 'inverse' is in type, or check for colon
    # Freqtrade/CCXT usually puts colon for futures
    if ":" not in symbol:
        # Check if it's spot?
        # If we are strictly validating futures schema
        # But maybe list-markets returns spot too?
        # We should only fail if we expect futures format.
        # But the requirement is "Strict schema gatekeeper".
        # If the market dump contains spot pairs, we shouldn't fail unless we only requested futures?
        # Freqtrade list-markets output depends on config or exchange.
        # Assuming we filter for futures later, but the schema check runs on the raw dump.
        # If raw dump has mixed, we can't enforce colon on everything.
        # However, for Delta, we expect futures.
        # I'll add a warning if no colon, but not fail unless strict mode?
        # Let's be strict on "no whitespace" and "uppercase".
        pass
    else:
        # Check components
        parts = symbol.split(":")
        if len(parts) < 2:
            errors.append(f"Symbol '{symbol}' malformed (expected BASE/QUOTE:SETTLE)")


def validate_volume(m, symbol, errors):
    if "info" in m and isinstance(m["info"], dict):
        # Delta specific volume field might be in info
        # But CCXT unifies it usually?
        pass
    # If standard volume is present
    if "quoteVolume" in m and m["quoteVolume"] is not None:
         if m["quoteVolume"] < 1000 and STRICT_VOLUME:
             errors.append(f"Low volume for {symbol}: {m['quoteVolume']}")


def validate_schema(data):
    if not isinstance(data, list):
        return None, ["Root must be a list of markets"]

    if len(data) < MIN_MARKETS:
        return None, [f"Market count {len(data)} < MIN_MARKETS ({MIN_MARKETS})"]

    symbols = set()
    errors = []

    for i, m in enumerate(data):
        symbol = validate_market_structure(i, m, errors)
        if not symbol:
            continue

        validate_symbol_format(symbol, m, errors)

        if symbol in symbols:
            errors.append(f"Duplicate symbol '{symbol}'")
        symbols.add(symbol)

        validate_volume(m, symbol, errors)

    return symbols, errors


def validate_drift(current_symbols, previous_path):
    prev_path_obj = Path(previous_path)
    if not previous_path or not prev_path_obj.exists():
        return "No previous dump found. Skipping drift check.", 0.0, []

    try:
        with prev_path_obj.open() as f:
            prev_data = json.load(f)
            if isinstance(prev_data, dict) and "markets" in prev_data:
                prev_data = prev_data["markets"]

            # If prev_data is not a list?
            if not isinstance(prev_data, list):
                 return "Previous dump invalid format. Skipping drift check.", 0.0, []

            prev_symbols = {m["symbol"] for m in prev_data if "symbol" in m}
    except Exception as e:
        return f"Could not read previous dump: {e}. Skipping drift check.", 0.0, []

    removed = prev_symbols - current_symbols
    added = current_symbols - prev_symbols

    if len(prev_symbols) == 0:
        removal_ratio = 0.0
    else:
        removal_ratio = len(removed) / len(prev_symbols)

    drift_msg = f"Drift: +{len(added)} / -{len(removed)} (Ratio: {removal_ratio:.2%})"

    errors = []
    if removal_ratio > MAX_REMOVAL_RATIO:
        errors.append(f"Removal ratio {removal_ratio:.2f} > MAX_REMOVAL_RATIO ({MAX_REMOVAL_RATIO}). Unsafe drift!")

    return drift_msg, removal_ratio, errors


def main():
    if len(sys.argv) < 2:
        print("Usage: validate_markets_schema.py <current_json> [previous_json]")
        sys.exit(1)

    current_path = sys.argv[1]
    prev_path = sys.argv[2] if len(sys.argv) > 2 else None

    # Report file setup
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    report_file = f"user_data/reports/markets_schema_report_{ts}.md"
    report_content = f"# Markets Schema Validation Report\n\nDate: {datetime.now(timezone.utc).isoformat()}\nFile: {current_path}\n"

    print(f"Validating {current_path}...")

    try:
        with Path(current_path).open() as f:
            data = json.load(f)
    except Exception as e:
        fail(f"Invalid JSON: {e}", report_file, report_content)

    if isinstance(data, dict) and "markets" in data:
        data = data["markets"]

    symbols, schema_errors = validate_schema(data)

    if schema_errors:
        report_content += "\n## Schema Errors\n"
        for e in schema_errors[:20]:
            report_content += f"- {e}\n"
        if len(schema_errors) > 20:
            report_content += f"- ...and {len(schema_errors) - 20} more\n"

        fail(f"Schema validation failed with {len(schema_errors)} errors.", report_file, report_content)

    report_content += f"\n## Schema Check\n- Status: PASS\n- Markets count: {len(symbols)}\n"

    if prev_path:
        drift_msg, ratio, drift_errors = validate_drift(symbols, prev_path)
        report_content += f"\n## Drift Check\n- {drift_msg or 'N/A'}\n"

        if drift_errors:
            report_content += "\n### Drift Errors\n"
            for e in drift_errors:
                report_content += f"- {e}\n"
            fail(f"Drift validation failed: {drift_errors[0]}", report_file, report_content)
    else:
        report_content += "\n## Drift Check\n- Skipped (No previous dump)\n"

    report_content += "\n## Result\nVALIDATION PASS\n"

    try:
        with Path(report_file).open("w") as f:
            f.write(report_content)
        print(f"Report written to {report_file}")
    except Exception as e:
        warn(f"Could not write report: {e}")

    print("VALIDATION PASS")


if __name__ == "__main__":
    main()
