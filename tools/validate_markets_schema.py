#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

# Configuration defaults
DEFAULT_MIN_MARKETS = 20
DEFAULT_MAX_REMOVAL_RATIO = 0.25
DEFAULT_STRICT_VOLUME = False

REQUIRED_FIELDS = ["symbol", "base", "quote", "active"]
REQUIRED_TYPE_FIELDS = ["type", "contract", "future", "perp", "spot", "linear"]


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

    # Check for at least one type indicator
    # Freqtrade dump from CCXT usually has 'type', 'linear', 'contract' etc.
    if not any(f in m for f in REQUIRED_TYPE_FIELDS):
        errors.append(f"Item {i} missing type indicator (one of {REQUIRED_TYPE_FIELDS})")

    symbol = m.get("symbol", "")
    if not symbol:
        errors.append(f"Item {i} has empty symbol")
        return None
    return symbol


def validate_symbol_format(symbol, errors, strict_futures=True):
    # Symbol format: BASE/QUOTE:SETTLE for futures usually
    # Reject whitespace/lowercase
    if re.search(r"\s", symbol):
        errors.append(f"Symbol '{symbol}' contains whitespace")
    if symbol != symbol.upper():
        errors.append(f"Symbol '{symbol}' is not uppercase")

    # Strict check for futures format (must have settle currency)
    # Only if it looks like a standard pair, avoid checking indices if they differ significantly
    if strict_futures and ":" not in symbol:
         errors.append(f"Symbol '{symbol}' missing settle delimiter (:)")


def validate_volume(m, symbol, errors, strict_volume):
    # Volume check
    if "volume" in m:
        vol = m.get("volume")
        # Check for invalid numeric types
        if not isinstance(vol, (int, float)) and vol is not None:
             # Some exchanges might return strings, try to parse?
             # CCXT usually returns floats.
             pass

        if isinstance(vol, (int, float)):
            if vol < 0:
                errors.append(f"Negative volume for {symbol}: {vol}")
            elif strict_volume and vol < 1000:
                errors.append(f"Low volume for {symbol}: {vol}")
            elif not strict_volume and vol < 1000:
                warn(f"Low volume for {symbol}: {vol}")


def validate_environment_sanity(data, env):
    # Check for exchange metadata if available
    # freqtrade list-markets output might be a list or a dict

    # Delta environment URLs keywords
    env_keywords = {
        "india_prod": ["india", "ind"],
        "global_prod": ["delta.exchange"],
        "india_testnet": ["testnet", "test"]
    }

    keywords = env_keywords.get(env, [])
    if not keywords:
        warn(f"Unknown DELTA_ENV '{env}', skipping environment sanity check.")
        return

    # Helper to check string for keywords
    def matches_env(s):
        if not s: return False
        s = str(s).lower()
        return any(k in s for k in keywords)

    # If data is a dict and has 'exchange_id' or 'urls'
    if isinstance(data, dict):
        if "urls" in data:
            urls = str(data["urls"])
            if not matches_env(urls):
                warn(f"Environment mismatch? URLs {urls} do not contain keywords {keywords}")

        # If 'info' is available in the first market
        if "markets" in data and len(data["markets"]) > 0:
            first_market = data["markets"][0]
            if "info" in first_market:
                info = str(first_market["info"])
                # This is a weak check, as 'info' might not contain URL.
                pass
    elif isinstance(data, list) and len(data) > 0:
        # Check first market info if available
        first_market = data[0]
        # Can't easily determine env from market data alone without exchange metadata
        pass


def validate_drift(current_symbols, previous_path, max_removal_ratio):
    prev_path_obj = Path(previous_path)
    if not previous_path or not prev_path_obj.exists():
        print("No previous whitelist found. Skipping drift check.")
        return [], 0.0, 0

    try:
        with prev_path_obj.open() as f:
            prev_data = json.load(f)

        if isinstance(prev_data, dict) and "exchange" in prev_data:
            prev_symbols = set(prev_data["exchange"].get("pair_whitelist", []))
        elif isinstance(prev_data, list):
            prev_symbols = set(prev_data)
        else:
             warn("Previous whitelist format unrecognized. Skipping drift check.")
             return [], 0.0, 0

    except Exception as e:
        warn(f"Could not read previous whitelist: {e}")
        return [], 0.0, 0

    if not prev_symbols:
        return [], 0.0, 0

    removed = prev_symbols - current_symbols
    added = current_symbols - prev_symbols

    removal_ratio = len(removed) / len(prev_symbols) if len(prev_symbols) > 0 else 0.0

    print(f"Drift stats: +{len(added)} / -{len(removed)} (Ratio: {removal_ratio:.2f})")

    drift_errors = []
    if removal_ratio > max_removal_ratio:
        drift_errors.append(
            f"Large delist drift: {removal_ratio:.2f} > MAX_REMOVAL_RATIO ({max_removal_ratio}). Manual review required."
        )

    return drift_errors, removal_ratio, len(removed)


def write_report(path, status, stats, errors, drift_errors):
    report = f"""# Markets Schema Validation Report
Date: {datetime.now(UTC).isoformat()}
Status: {status}

## Summary
- Total Markets: {stats['total']}
- Eligible Markets: {stats['eligible']}
- Whitelist Size: {stats['whitelist_size']}
- Drift: {stats['drift_removed']} removed, ratio {stats['drift_ratio']:.2f}

## Validation Errors
"""
    if errors:
        for e in errors:
            report += f"- {e}\n"
    else:
        report += "None\n"

    report += "\n## Drift Errors\n"
    if drift_errors:
        for e in drift_errors:
            report += f"- {e}\n"
    else:
        report += "None\n"

    try:
        with Path(path).open("w") as f:
            f.write(report)
        print(f"Report written to {path}")
    except Exception as e:
        warn(f"Could not write report: {e}")


def main():
    parser = argparse.ArgumentParser(description="Validate markets schema and check for drift.")
    parser.add_argument("--markets", required=True, help="Path to markets JSON dump")
    parser.add_argument("--prev-whitelist", help="Path to previous whitelist JSON")
    parser.add_argument("--env", help="Delta Environment (india_prod, global_prod, india_testnet)")
    parser.add_argument("--out-report", required=True, help="Path to output Markdown report")

    args = parser.parse_args()

    # Load Config from Env or Defaults
    min_markets = int(os.environ.get("MIN_MARKETS", DEFAULT_MIN_MARKETS))
    max_removal_ratio = float(os.environ.get("MAX_REMOVAL_RATIO", DEFAULT_MAX_REMOVAL_RATIO))
    strict_volume = os.environ.get("STRICT_VOLUME", str(DEFAULT_STRICT_VOLUME)).lower() == "true"

    print(f"Validating {args.markets} for env {args.env}...")

    # Initialize stats to avoid reference before assignment in exception block
    stats = {'total': 0, 'eligible': 0, 'whitelist_size': 0, 'drift_removed': 0, 'drift_ratio': 0.0}

    try:
        with Path(args.markets).open() as f:
            data = json.load(f)
    except Exception as e:
        write_report(args.out_report, "FAIL", stats, [f"Invalid JSON: {e}"], [])
        fail(f"Invalid JSON: {e}")

    # Handle data structure
    if isinstance(data, dict) and "markets" in data:
        markets_list = data["markets"]
    elif isinstance(data, list):
        markets_list = data
    else:
        write_report(args.out_report, "FAIL", stats, ["Root must be a list of markets or dict with 'markets' key"], [])
        fail("Invalid market data structure")

    if len(markets_list) < min_markets:
        stats['total'] = len(markets_list)
        write_report(args.out_report, "FAIL", stats, [f"Market count {len(markets_list)} < MIN_MARKETS ({min_markets})"], [])
        fail(f"Market count {len(markets_list)} < MIN_MARKETS ({min_markets})")

    validate_environment_sanity(data, args.env)

    symbols = set()
    errors = []
    eligible_count = 0

    for i, m in enumerate(markets_list):
        # Structure check
        symbol = validate_market_structure(i, m, errors)
        if not symbol:
            continue

        is_active = m.get("active", False)

        # Only validate format for active symbols
        if is_active:
            # We assume active symbols should follow the standard format
            validate_symbol_format(symbol, errors, strict_futures=True)
            eligible_count += 1
            validate_volume(m, symbol, errors, strict_volume)

        # Uniqueness check (case-insensitive)
        if symbol.upper() in symbols:
            errors.append(f"Duplicate symbol '{symbol}'")
        symbols.add(symbol.upper())

    # Drift Check
    drift_errors = []
    removal_ratio = 0.0
    removed_count = 0

    # We only check drift against the "eligible" (active) symbols we just collected
    if args.prev_whitelist:
        # Pass the set of currently active valid symbols
        drift_errors, removal_ratio, removed_count = validate_drift(symbols, args.prev_whitelist, max_removal_ratio)

    stats = {
        'total': len(markets_list),
        'eligible': eligible_count,
        'whitelist_size': len(symbols),
        'drift_removed': removed_count,
        'drift_ratio': removal_ratio
    }

    status = "PASS"
    if errors or drift_errors:
        status = "FAIL"

    write_report(args.out_report, status, stats, errors, drift_errors)

    if status == "FAIL":
        fail("Validation failed. See report for details.")
    else:
        print("VALIDATION PASS")
        sys.exit(0)


if __name__ == "__main__":
    main()
