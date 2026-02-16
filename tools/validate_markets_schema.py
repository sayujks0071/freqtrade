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
DEFAULT_FILTER_MODE = "perps_usdt"


def get_env_bool(key, default=False):
    val = os.environ.get(key, str(default)).lower()
    return val in ("true", "1", "yes", "on")


MIN_MARKETS = int(os.environ.get("MIN_MARKETS", DEFAULT_MIN_MARKETS))
MAX_REMOVAL_RATIO = float(os.environ.get("MAX_REMOVAL_RATIO", DEFAULT_MAX_REMOVAL_RATIO))
STRICT_VOLUME = get_env_bool("STRICT_VOLUME", DEFAULT_STRICT_VOLUME)
FILTER_MODE = os.environ.get("FILTER_MODE", DEFAULT_FILTER_MODE)
ALLOWLIST_REGEX = os.environ.get("ALLOWLIST_REGEX", ".*")

REQUIRED_FIELDS = ["symbol", "base", "quote", "active"]


def fail(message):
    print(f"FAIL: {message}")
    sys.exit(2)


def warn(message):
    print(f"WARN: {message}")


def is_eligible(market):
    """
    Check if market is eligible for whitelist based on FILTER_MODE.
    Duplicated logic from tools/generate_whitelist.py to keep validator self-contained.
    """
    symbol = market.get("symbol", "")
    # Basic active check - defaults to True if missing, but usually explicit
    if not market.get("active", True):
        return False

    # Filter logic
    if FILTER_MODE == "perps_usdt":
        # Check if quote is USDT and it's a perp
        return "/USDT:USDT" in symbol
    elif FILTER_MODE == "all_futures":
        return True
    elif FILTER_MODE == "allowlist_regex":
        return bool(re.match(ALLOWLIST_REGEX, symbol))
    else:
        # Default to perps_usdt
        return "/USDT:USDT" in symbol


def validate_market_structure(i, m, errors):
    # Required fields
    for f in REQUIRED_FIELDS:
        if f not in m:
            errors.append(f"Item {i} missing field '{f}'")

    # type / contract / future/perp indicator (at least one)
    type_indicators = ["type", "contract", "future", "perp", "spot", "swap", "linear"]
    if not any(k in m for k in type_indicators):
        errors.append(f"Item {i} missing type/contract indicator")

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

    # Strict check for futures format (must have settle delimiter) if we are in a futures mode
    # If FILTER_MODE implies futures, we expect :
    if FILTER_MODE in ("perps_usdt", "all_futures") and ":" not in symbol:
        errors.append(f"Symbol '{symbol}' missing settle delimiter (:)")


def validate_volume(m, symbol, errors):
    # Reject markets with clearly invalid numeric fields (NaN, negative, absurdly huge)
    # Check common numeric fields if present
    numeric_fields = ["volume", "vwap", "open", "close", "high", "low"]
    for field in numeric_fields:
        if field in m:
            val = m[field]
            if val is None:
                continue
            if not isinstance(val, (int, float)):
                # Some dumps might have strings, try to convert? CCXT usually floats.
                try:
                    val = float(val)
                except (ValueError, TypeError):
                    errors.append(f"Symbol '{symbol}' field '{field}' is not numeric: {val}")
                    continue

            if val < 0:
                errors.append(f"Symbol '{symbol}' field '{field}' is negative: {val}")
            # NaN check
            if val != val:  # NaN check
                errors.append(f"Symbol '{symbol}' field '{field}' is NaN")

    # Strict volume check
    if STRICT_VOLUME and "volume" in m:
        vol = m.get("volume")
        if (
            vol is not None
            and isinstance(vol, (int, float))
            and vol < 1.0  # Arbitrary small number or 0?
        ):
            # "Optionally filter out near-zero volume markets... only warn by default"
            # Here we are in strict mode so we error?
            # "allow STRICT_VOLUME=true to fail if too many are illiquid"
            # For now let's just flag it as error in strict mode
            errors.append(f"Low volume for {symbol}: {vol}")


def validate_environment_sanity(data, expected_env):
    # E) Environment sanity
    # Try to find metadata in the dump.
    # Freqtrade list-markets usually returns a list of market dicts.
    # It does not contain global exchange metadata.
    # So we cannot easily verify if we are connected to the correct environment
    # just from the market list.
    warn(
        f"Environment check skipped: Metadata not available in market list dump for {expected_env}."
    )


def validate_drift(current_symbols, previous_path):
    drift_info = {"added": [], "removed": [], "ratio": 0.0, "drift_safe": True, "msg": ""}

    if not previous_path or not Path(previous_path).exists():
        drift_info["msg"] = "No previous whitelist found. Skipping drift check."
        return drift_info

    try:
        with Path(previous_path).open() as f:
            prev_data = json.load(f)
            # Handle if previous whitelist is simple list or dict
            # Freqtrade whitelist format: {"exchange": {"pair_whitelist": [...]}}
            if isinstance(prev_data, dict) and "exchange" in prev_data:
                prev_symbols = set(prev_data["exchange"].get("pair_whitelist", []))
            elif isinstance(prev_data, list):
                prev_symbols = set(prev_data)
            else:
                # Could be raw market dump used as prev whitelist?
                # If so, extract symbols.
                if (
                    isinstance(prev_data, list)
                    and isinstance(prev_data[0], dict)
                    and "symbol" in prev_data[0]
                ):
                    prev_symbols = {m["symbol"] for m in prev_data if is_eligible(m)}
                else:
                    prev_symbols = set()
    except Exception as e:
        drift_info["msg"] = f"Could not read previous whitelist: {e}"
        return drift_info

    if not prev_symbols:
        drift_info["msg"] = "Previous whitelist empty. Skipping drift check."
        return drift_info

    removed = prev_symbols - current_symbols
    added = current_symbols - prev_symbols

    removal_ratio = len(removed) / len(prev_symbols) if len(prev_symbols) > 0 else 0.0

    drift_info["added"] = sorted(list(added))
    drift_info["removed"] = sorted(list(removed))
    drift_info["ratio"] = removal_ratio

    if removal_ratio > MAX_REMOVAL_RATIO:
        drift_info["drift_safe"] = False
        drift_info["msg"] = (
            f"Large delist drift: {removal_ratio:.2f} > {MAX_REMOVAL_RATIO}. "
            f"Removed {len(removed)}/{len(prev_symbols)} pairs."
        )
    else:
        drift_info["msg"] = f"Drift safe. Ratio: {removal_ratio:.2f}"

    return drift_info


def load_markets(path):
    if not Path(path).exists():
        fail(f"Markets file {path} does not exist")

    try:
        with Path(path).open() as f:
            data = json.load(f)
    except Exception as e:
        fail(f"Invalid JSON in {path}: {e}")

    # Handle both dict (freqtrade wrapper) and list
    if isinstance(data, dict):
        if "markets" in data:
            return data["markets"]
        else:
            # Maybe it is a dict of markets keyed by symbol?
            if data and isinstance(next(iter(data.values())), dict):
                return list(data.values())
            else:
                fail("Root is dict but no 'markets' key and values don't look like markets")
    elif isinstance(data, list):
        return data
    else:
        fail("Root must be a list or dict")


def write_report(path, status, env, markets_file, total, eligible, drift_result, errors):
    added_str = ", ".join(drift_result["added"][:10]) + (
        "..." if len(drift_result["added"]) > 10 else ""
    )
    removed_str = ", ".join(drift_result["removed"][:10]) + (
        "..." if len(drift_result["removed"]) > 10 else ""
    )

    report_content = f"""# Markets Schema Validation Report
**Date:** {datetime.now(UTC).isoformat()}
**Status:** {status}
**Environment:** {env}
**File:** {markets_file}

## Statistics
- Total Markets: {total}
- Eligible Markets: {eligible}
- Whitelist Drift Ratio: {drift_result["ratio"]:.2f} (Limit: {MAX_REMOVAL_RATIO})

## Drift Analysis
- **Added ({len(drift_result["added"])}):** {added_str}
- **Removed ({len(drift_result["removed"])}):** {removed_str}
- **Message:** {drift_result["msg"]}

## Validation Errors
"""
    if errors:
        report_content += "\n".join(f"- {e}" for e in errors[:50])
        if len(errors) > 50:
            report_content += f"\n- ... and {len(errors) - 50} more"
    else:
        report_content += "No validation errors."

    try:
        with Path(path).open("w") as f:
            f.write(report_content)
        print(f"Report written to {path}")
    except Exception as e:
        warn(f"Could not write report: {e}")


def main():
    parser = argparse.ArgumentParser(description="Validate market schema and drift.")
    parser.add_argument("--markets", required=True, help="Path to markets JSON dump")
    parser.add_argument(
        "--candidate-whitelist",
        help="Path to candidate whitelist (not used, generating implicit candidate list)",
    )
    parser.add_argument("--prev-whitelist", help="Path to previous whitelist JSON")
    parser.add_argument("--env", help="Target Environment (e.g., india_prod)", default="india_prod")
    parser.add_argument("--out-report", help="Path to output markdown report", required=True)

    args = parser.parse_args()

    print(f"Validating {args.markets} for env {args.env}...")

    markets_data = load_markets(args.markets)

    # B) Non-empty markets count >= MIN_MARKETS
    total_markets = len(markets_data)
    if total_markets < MIN_MARKETS:
        fail(f"Total market count {total_markets} < MIN_MARKETS ({MIN_MARKETS})")

    # E) Environment sanity
    validate_environment_sanity(markets_data, args.env)

    # C) Validate each eligible market
    eligible_symbols = set()
    errors = []

    for i, m in enumerate(markets_data):
        # Validate structure first
        symbol = validate_market_structure(i, m, errors)
        if not symbol:
            continue

        # Check eligibility for whitelist
        if is_eligible(m):
            validate_symbol_format(symbol, errors)

            if symbol in eligible_symbols:
                errors.append(f"Duplicate eligible symbol '{symbol}'")
            eligible_symbols.add(symbol)

            # D) Volume/Numeric checks
            validate_volume(m, symbol, errors)

    # F) Drift check
    drift_result = validate_drift(eligible_symbols, args.prev_whitelist)

    if not drift_result["drift_safe"]:
        # Only fail if drift is unsafe
        errors.append(drift_result["msg"])

    # Generate Report
    status = "PASS"
    if errors:
        status = "FAIL"

    write_report(
        args.out_report,
        status,
        args.env,
        args.markets,
        total_markets,
        len(eligible_symbols),
        drift_result,
        errors,
    )

    # Final Exit
    if status == "FAIL":
        print("Validation FAILED. See report for details.")
        sys.exit(2)
    else:
        print("Validation PASSED.")
        sys.exit(0)


if __name__ == "__main__":
    main()
