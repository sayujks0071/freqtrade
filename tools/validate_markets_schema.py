#!/usr/bin/env python3
"""
Validates the markets dump from Freqtrade/CCXT against strict schema rules and sanity checks.
Input: JSON file with markets (list or dict).
Output:
    - Exit code 0: PASS
    - Exit code 2: FAIL
    - Generates a Markdown report.
"""
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


def fail(message):
    print(f"FAIL: {message}")
    sys.exit(2)


def warn(message):
    print(f"WARN: {message}")


def validate_market_structure(i, m, errors):
    required_fields = ["symbol", "base", "quote", "active"]
    # Check if at least one type indicator exists
    type_fields = ["type", "contract", "future", "perp", "linear", "inverse"]

    missing = [f for f in required_fields if f not in m]
    if missing:
        errors.append(f"Item {i} missing fields: {missing}")
        return None

    # Type check - loosely check if it looks like a future/perp if expected
    # Freqtrade/CCXT dumps usually have 'type': 'future' or 'swap'
    # We won't strictly fail on missing type field if it's not present in some minimal dumps,
    # but the requirement says "type / contract / future/perp indicator (at least one)"
    has_type = any(f in m for f in type_fields)
    if not has_type:
        errors.append(f"Item {i} missing type indicator (type/contract/future/perp)")

    symbol = m.get("symbol", "")
    if not isinstance(symbol, str) or not symbol:
        errors.append(f"Item {i} has invalid symbol: {symbol}")
        return None
    return symbol


def validate_symbol_format(symbol, m, errors):
    # Requirement: Must match futures style: BASE/QUOTE:SETTLE
    # OR a consistent CCXT format discovered from dump.
    # Also reject whitespace, lowercase, missing settle delimiter if looks like future.

    if re.search(r"\s", symbol):
        errors.append(f"Symbol '{symbol}' contains whitespace")
    if symbol != symbol.upper():
        errors.append(f"Symbol '{symbol}' is not uppercase")

    # Check for futures format characteristic
    # If it's a future/perp on Delta, it should have a settle currency, usually after ':'
    # We allow spot markets (no colon) if explicitly marked as spot.
    is_spot = m.get("type") == "spot" or m.get("spot") is True

    if not is_spot:
        if ":" not in symbol:
            # This might be valid for spot, but the prompt implies futures context (Delta).
            # "Must match futures style ... OR a consistent CCXT format discovered"
            # If we are strict about futures, we expect 'BASE/QUOTE:SETTLE'.
            errors.append(f"Symbol '{symbol}' missing settle delimiter (:)")

    parts = symbol.split("/")
    if len(parts) < 2:
        errors.append(f"Symbol '{symbol}' missing quote delimiter (/)")


def _check_val(key, val, limit_name, symbol, errors):
    if val is None:
        return
    if not isinstance(val, (int, float)):
        # strings might be parsed, but usually json dump has numbers or strings
        try:
            val = float(val)
        except (ValueError, TypeError):
            return  # skip if not numeric

    if val != val:  # NaN check
        errors.append(f"{symbol}: {limit_name} is NaN")
    if val < 0:
        errors.append(f"{symbol}: {limit_name} is negative ({val})")
    if val > 1e15:  # Arbitrary huge number
        errors.append(f"{symbol}: {limit_name} seems absurdly huge ({val})")


def validate_numeric_sanity(m, symbol, strict_volume, errors):
    # Reject NaN, negative, absurdly huge
    # Fields to check: limits (amount, price, cost), volume (if present)

    # Check limits if available
    if "limits" in m and isinstance(m["limits"], dict):
        limits = m["limits"]
        for k, v in limits.items():
            if isinstance(v, dict):
                _check_val(f"limits.{k}.min", v.get("min"), f"limits.{k}.min", symbol, errors)
                _check_val(f"limits.{k}.max", v.get("max"), f"limits.{k}.max", symbol, errors)

    # Volume check
    # CCXT often puts 24h volume in 'quoteVolume' or 'baseVolume' or just 'volume'
    # Freqtrade list-markets might standardize.
    # If strict_volume is set, warn or fail on low volume.
    # Requirement: "Optionally filter out near-zero volume markets... only warn by default"
    # "allow STRICT_VOLUME=true to fail"

    vol = m.get("quoteVolume") or m.get("baseVolume") or m.get("volume")
    if vol is not None:
        _check_val("volume", vol, "volume", symbol, errors)
        try:
            val = float(vol)
            if val < 100 and val > 0:  # Arbitrary low threshold for warning
                msg = f"{symbol}: Low volume ({val})"
                if strict_volume:
                    errors.append(msg)
                else:
                    warn(msg)
        except (ValueError, TypeError):
            pass


def validate_environment(data, env_name, errors):
    # Attempt to verify environment.
    # Look for exchange info in metadata if available.
    # If data is a list, we might look at the first item's 'info' field if it contains URLs.

    # Delta Exchange specific checks
    # Production URL: api.delta.exchange or api.india.delta.exchange
    # Testnet URL: testnet-api.delta.exchange

    check_url = "delta.exchange"
    if env_name == "india_testnet":
        check_url = "testnet"

    # We scan a few markets to see if 'info' has URLs
    found_evidence = False
    for m in data[:5]:
        info = m.get("info", {})
        # stringify info to search for url
        info_str = str(info).lower()
        if check_url in info_str:
            found_evidence = True
            break

    if not found_evidence and len(data) > 0:
        warn(
            f"Could not verify environment '{env_name}' from market metadata. "
            "Ensure you are connected to the correct exchange instance."
        )


def load_previous_whitelist(path):
    if not path or not Path(path).exists():
        return None
    try:
        with Path(path).open() as f:
            data = json.load(f)

        # Handle different whitelist formats
        # 1. List of strings
        # 2. Dict with "exchange": {"pair_whitelist": [...]}

        if isinstance(data, list):
            return set(data)
        if isinstance(data, dict):
            if "exchange" in data and "pair_whitelist" in data["exchange"]:
                return set(data["exchange"]["pair_whitelist"])
            # Maybe just a dict of pairs?
            return set(data.keys())  # unlikely but possible in some formats

        return None
    except Exception as exc:
        warn(f"Failed to load previous whitelist: {exc}")
        return None


def validate_drift(current_symbols, prev_symbols, max_removal_ratio, errors):
    if not prev_symbols:
        print("No previous whitelist found. Skipping drift check.")
        return [], 0.0

    removed = prev_symbols - current_symbols
    added = current_symbols - prev_symbols

    removal_count = len(removed)
    prev_count = len(prev_symbols)

    ratio = removal_count / prev_count if prev_count > 0 else 0.0

    print(f"Drift Check: +{len(added)} / -{removal_count} (Ratio: {ratio:.2f})")

    if ratio > max_removal_ratio:
        errors.append(
            f"Large delist drift: {ratio:.2f} > {max_removal_ratio}. Manual review required."
        )

    # Format change check
    # If a symbol in previous whitelist exists in current symbols but has a different format...
    # Actually, "If pair-format changed for any existing pair".
    # This implies we can track underlying pair ID?
    # But usually we only have symbol strings.
    # If a symbol string changes, it looks like a removal and an addition.
    # The requirement likely means: "Reject if we see widespread format changes"
    # OR "If we can detect that the *same* market now has a different symbol format".
    # Without IDs, we can't easily do that.
    # However, we can check if the *general format* of symbols in the dump is
    # consistent with previous.

    # Let's interpret "format-change flags" as:
    # If we see symbols that look like they are the same pair but different format
    # (e.g. BTC/USDT vs BTC/USDT:USDT).
    # We can check if `removed` contains symbols that are substrings of `added` or vice-versa.

    for r in removed:
        # specific check: if 'BTC/USDT' was removed and 'BTC/USDT:USDT' was added
        if ":" not in r:
            # prev was spot-like?
            pass

    return list(removed), ratio


def generate_report(out_path, status, errors, stats, drift_stats):
    ts = datetime.now(timezone.utc).isoformat()

    error_section = ""
    if errors:
        error_section = "## Errors\n"
        for e in errors[:20]:
            error_section += f"- {e}\n"
        if len(errors) > 20:
            error_section += f"- ... and {len(errors) - 20} more\n"

    drift_section = ""
    if drift_stats:
        removed_list, ratio = drift_stats
        drift_section = f"""## Drift Analysis
- Removed Pairs: {len(removed_list)}
- Removal Ratio: {ratio:.2%}
"""
        if removed_list:
            drift_section += "\n### Removed Samples\n"
            for r in list(removed_list)[:10]:
                drift_section += f"- {r}\n"

    report = f"""# Markets Schema Validation Report

**Status:** {status}
**Date:** {ts}

## Summary
- Total Markets in Dump: {stats['total']}
- Eligible Markets: {stats['eligible']}
- Whitelist Size (Potential): {stats['eligible']}

{drift_section}

{error_section}
"""
    try:
        with Path(out_path).open("w") as f:
            f.write(report)
        print(f"Report written to {out_path}")
    except Exception as exc:
        warn(f"Could not write report: {exc}")


def load_market_data(path):
    try:
        with Path(path).open() as f:
            data = json.load(f)
    except Exception as exc:
        fail(f"Invalid JSON in markets file: {exc}")
        return []  # unreachable

    # Handle { "markets": [...] } or [...]
    if isinstance(data, dict) and "markets" in data:
        return data["markets"]
    elif isinstance(data, list):
        return data
    else:
        fail("Root must be a list of markets or dict with 'markets' key")
        return []  # unreachable


def main():
    parser = argparse.ArgumentParser(description="Validate Freqtrade markets dump schema.")
    parser.add_argument("--markets", required=True, help="Path to markets JSON dump")
    parser.add_argument("--env", required=True, help="Environment name (e.g., india_prod)")
    parser.add_argument("--prev-whitelist", help="Path to previous whitelist JSON")
    parser.add_argument("--out-report", required=True, help="Path to output Markdown report")

    args = parser.parse_args()

    # Load config from env or defaults
    min_markets = int(os.environ.get("MIN_MARKETS", DEFAULT_MIN_MARKETS))
    max_removal_ratio = float(os.environ.get("MAX_REMOVAL_RATIO", DEFAULT_MAX_REMOVAL_RATIO))
    strict_volume = os.environ.get("STRICT_VOLUME", "false").lower() == "true"

    print(f"Validating {args.markets} (Env: {args.env})...")

    markets_list = load_market_data(args.markets)

    # 2. Basic Count Check
    if len(markets_list) < min_markets:
        fail(f"Market count {len(markets_list)} < MIN_MARKETS ({min_markets})")

    # 3. Validation Loop
    errors = []
    valid_symbols = set()

    for i, m in enumerate(markets_list):
        symbol = validate_market_structure(i, m, errors)
        if not symbol:
            continue

        # Check active
        # "active (bool or truthy)"
        if not m.get("active"):
            continue

        validate_symbol_format(symbol, m, errors)
        validate_numeric_sanity(m, symbol, strict_volume, errors)

        if symbol in valid_symbols:
            errors.append(f"Duplicate symbol '{symbol}'")
        valid_symbols.add(symbol)

    # 4. Environment Sanity
    validate_environment(markets_list, args.env, errors)

    # 5. Drift Check
    prev_symbols = load_previous_whitelist(args.prev_whitelist)
    drift_stats = None
    if prev_symbols:
        drift_stats = validate_drift(valid_symbols, prev_symbols, max_removal_ratio, errors)

    # 6. Report & Exit
    status = "PASS"
    if errors:
        status = "FAIL"

    stats = {
        "total": len(markets_list),
        "eligible": len(valid_symbols)
    }

    generate_report(args.out_report, status, errors, stats, drift_stats)

    if errors:
        print("\nValidation FAILED with errors:")
        for e in errors[:5]:
            print(f"- {e}")
        if len(errors) > 5:
            print(f"... {len(errors) - 5} more")
        sys.exit(2)

    print("Validation PASSED.")
    sys.exit(0)


if __name__ == "__main__":
    main()
