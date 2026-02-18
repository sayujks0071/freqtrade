#!/usr/bin/env python3
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def get_env(key, default):
    return os.environ.get(key, default)


def fail(message, report_file):
    print(f"FAIL: {message}")
    with report_file.open("a") as f:
        f.write(f"\n## FAILURE\n{message}\n")
    sys.exit(2)


def warn(message, report_file):
    print(f"WARN: {message}")
    with report_file.open("a") as f:
        f.write(f"\n## WARNING\n{message}\n")


def load_markets(markets_file, report_file):
    try:
        # Use Path.open()
        with Path(markets_file).open() as f:
            return json.load(f)
    except Exception as e:
        # Create a basic report file even on JSON fail to log the error
        with report_file.open("a") as f:
            f.write(f"Invalid JSON: {e}\n")
        print(f"FAIL: Invalid JSON: {e}")
        sys.exit(2)


def validate_market_fields(market, required_fields, report_file):
    for field in required_fields:
        if field not in market:
            fail(
                f"Missing field '{field}' in market: {market.get('symbol', 'UNKNOWN')}",
                report_file,
            )


def validate_market_format(market, filter_mode, report_file):
    symbol = market["symbol"]
    if filter_mode in ["perps_usdt", "all_futures"]:
        if ":" not in symbol:
            fail(
                f"Invalid symbol format for futures (missing colon): {symbol}",
                report_file,
            )
        parts = symbol.split(":")
        if len(parts) != 2:
            fail(f"Invalid symbol format (too many colons): {symbol}", report_file)
        if not parts[1]:
            fail(f"Invalid symbol format (empty settle currency): {symbol}", report_file)


def validate_schema(markets, min_markets, filter_mode, strict_volume, report_file):
    if not isinstance(markets, list):
        fail("Markets dump must be a list", report_file)

    if len(markets) < min_markets:
        fail(f"Too few markets: {len(markets)} < {min_markets}", report_file)

    required_fields = ["symbol", "base", "quote", "active"]
    symbols = set()
    active_count = 0

    for m in markets:
        validate_market_fields(m, required_fields, report_file)

        symbol = m["symbol"]

        if symbol.lower() in [s.lower() for s in symbols]:
            fail(f"Duplicate symbol found: {symbol}", report_file)
        symbols.add(symbol)

        if m.get("active"):
            active_count += 1

        validate_market_format(m, filter_mode, report_file)

        if strict_volume:
            # Try to find volume
            pass


def check_drift(markets, prev_markets_file, max_removal_ratio, report_file):
    prev_path = Path(prev_markets_file) if prev_markets_file else None

    if prev_path and prev_path.exists():
        try:
            with prev_path.open() as f:
                prev_markets = json.load(f)

            prev_symbols = {m["symbol"] for m in prev_markets if m.get("active")}
            curr_symbols = {m["symbol"] for m in markets if m.get("active")}

            removed = prev_symbols - curr_symbols
            added = curr_symbols - prev_symbols

            removal_ratio = len(removed) / len(prev_symbols) if len(prev_symbols) > 0 else 0.0

            with report_file.open("a") as f:
                f.write("\n## Drift Analysis\n")
                f.write(f"- Previous Active: {len(prev_symbols)}\n")
                f.write(f"- Current Active: {len(curr_symbols)}\n")
                f.write(f"- Removed: {len(removed)} ({removal_ratio:.2%})\n")
                f.write(f"- Added: {len(added)}\n")

            if removal_ratio > max_removal_ratio:
                fail(
                    f"Drift Safety Gate Triggered! Removed ratio {removal_ratio:.2%} "
                    f"> {max_removal_ratio}",
                    report_file,
                )

        except Exception as e:
            warn(f"Could not perform drift check: {e}", report_file)


def main():
    if len(sys.argv) < 2:
        print("Usage: validate_markets_schema.py <markets_file> [prev_markets_file]")
        sys.exit(1)

    markets_file = sys.argv[1]
    prev_markets_file = sys.argv[2] if len(sys.argv) > 2 else None

    # Use datetime.UTC where possible or timezone.utc
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")  # noqa: UP017
    report_file = Path(f"user_data/reports/whitelist_diff_{timestamp}.md")

    # Environment configs
    MIN_MARKETS = int(get_env("MIN_MARKETS", 20))
    MAX_REMOVAL_RATIO = float(get_env("MAX_REMOVAL_RATIO", 0.25))
    STRICT_VOLUME = get_env("STRICT_VOLUME", "false").lower() == "true"
    FILTER_MODE = get_env("FILTER_MODE", "perps_usdt")

    # Ensure report directory exists
    report_file.parent.mkdir(parents=True, exist_ok=True)

    with report_file.open("w") as f:
        f.write(f"# Market Schema Validation Report\nDate: {timestamp}\nFile: {markets_file}\n\n")

    markets = load_markets(markets_file, report_file)
    validate_schema(markets, MIN_MARKETS, FILTER_MODE, STRICT_VOLUME, report_file)
    check_drift(markets, prev_markets_file, MAX_REMOVAL_RATIO, report_file)

    print("Validation PASSED.")
    sys.exit(0)


if __name__ == "__main__":
    main()
