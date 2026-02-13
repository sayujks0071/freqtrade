#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path


# Configuration
MIN_MARKETS = int(os.environ.get("MIN_MARKETS", 20))
# Drift ratio is handled in drift check logic
MAX_REMOVAL_RATIO = float(os.environ.get("MAX_REMOVAL_RATIO", 0.25))
STRICT_VOLUME = os.environ.get("STRICT_VOLUME", "false").lower() == "true"
FILTER_MODE = os.environ.get("FILTER_MODE", "perps_usdt")
ALLOWLIST_REGEX = os.environ.get("ALLOWLIST_REGEX", ".*")

REQUIRED_FIELDS = ["symbol", "base", "quote", "active"]


def fail(message):
    print(f"FAIL: {message}")
    sys.exit(2)


def warn(message):
    print(f"WARN: {message}")


def is_eligible(m):
    # Check if market should be validated (and potentially whitelisted)
    # 1. Active check (default to True if missing, validated later)
    if not m.get("active", True):
        return False

    symbol = m.get("symbol", "")
    if not symbol:
        return False  # Can't determine eligibility without symbol

    if FILTER_MODE == "perps_usdt":
        # Strict check for USDT perps on Delta
        return "/USDT:USDT" in symbol
    elif FILTER_MODE == "all_futures":
        # Check type or symbol format
        type_ = m.get("type", "")
        if type_ in ["future", "linear", "inverse", "swap"]:
            return True
        if ":" in symbol:
            return True
        return False
    elif FILTER_MODE == "allowlist_regex":
        if re.match(ALLOWLIST_REGEX, symbol):
            return True
        return False

    # Default fallback
    return True


def validate_market_structure(i, m, errors):
    # Required fields
    for f in REQUIRED_FIELDS:
        if f not in m:
            errors.append(f"Item {i}: missing required field '{f}'")
            return None

    # Check for type/contract indicator (at least one)
    type_keys = ["type", "contract", "future", "perp", "spot", "linear", "inverse"]
    if not any(k in m for k in type_keys):
        errors.append(f"Item {i}: missing market type indicator (checked: {', '.join(type_keys)})")

    symbol = m.get("symbol", "")
    if not isinstance(symbol, str) or not symbol:
        errors.append(f"Item {i}: symbol is empty or not a string")
        return None

    return symbol


def validate_symbol_format(symbol, errors):
    # Symbol format: BASE/QUOTE:SETTLE for futures usually
    if re.search(r"\s", symbol):
        errors.append(f"Symbol '{symbol}' contains whitespace")

    if symbol != symbol.upper():
        errors.append(f"Symbol '{symbol}' is not uppercase")

    # Strict check for futures format (must have settle delimiter for Delta)
    # Only enforce if we expect futures/perps
    if FILTER_MODE in ["perps_usdt", "all_futures"] and ":" not in symbol:
        errors.append(f"Symbol '{symbol}' missing settle delimiter (:)")


def validate_volume(m, symbol, errors):
    vol = m.get("volume")
    if vol is None:
        return

    try:
        vol_float = float(vol)
    except (ValueError, TypeError):
        errors.append(f"Symbol '{symbol}' has invalid volume: {vol}")
        return

    if vol_float < 0:
        errors.append(f"Symbol '{symbol}' has negative volume: {vol_float}")

    if STRICT_VOLUME and vol_float < 1000:
        errors.append(f"Low volume for {symbol}: {vol_float} (STRICT_VOLUME=true)")


def validate_schema(data):
    if not isinstance(data, list):
        return ["Root must be a list of markets"], []

    # Count eligible markets
    eligible_count = 0
    symbols = set()
    errors = []

    for i, m in enumerate(data):
        if not is_eligible(m):
            continue

        eligible_count += 1
        symbol = validate_market_structure(i, m, errors)
        if not symbol:
            continue

        validate_symbol_format(symbol, errors)

        if symbol in symbols:
            errors.append(f"Duplicate symbol '{symbol}'")
        symbols.add(symbol)

        validate_volume(m, symbol, errors)

    if eligible_count < MIN_MARKETS:
        errors.append(f"Eligible market count {eligible_count} < MIN_MARKETS ({MIN_MARKETS})")

    return errors, symbols


def load_whitelist(path):
    try:
        with Path(path).open() as f:
            data = json.load(f)
    except Exception as e:
        warn(f"Could not read whitelist {path}: {e}")
        return set()

    if isinstance(data, list):
        return set(data)
    elif isinstance(data, dict):
        if "exchange" in data and "pair_whitelist" in data["exchange"]:
            return set(data["exchange"]["pair_whitelist"])
        pass

    return set()


def validate_drift(candidate_path, prev_path, errors):
    drift_stats = {}
    if not prev_path or not Path(prev_path).exists():
        print("No previous whitelist found. Skipping drift check.")
        return None

    candidate_symbols = load_whitelist(candidate_path)
    prev_symbols = load_whitelist(prev_path)

    if not prev_symbols:
        print("Previous whitelist is empty. Skipping drift check.")
        return None

    removed = prev_symbols - candidate_symbols
    added = candidate_symbols - prev_symbols

    removal_ratio = len(removed) / len(prev_symbols) if len(prev_symbols) > 0 else 0.0

    drift_stats = {
        "added_count": len(added),
        "removed_count": len(removed),
        "total_prev": len(prev_symbols),
        "total_cand": len(candidate_symbols),
        "ratio": removal_ratio,
        "removed_samples": list(removed)[:5],
        "added_samples": list(added)[:5],
        "format_changes": [],
    }

    if removal_ratio > MAX_REMOVAL_RATIO:
        errors.append(
            f"Drift Error: Removal ratio {removal_ratio:.2f} > "
            f"MAX_REMOVAL_RATIO ({MAX_REMOVAL_RATIO})"
        )
        errors.append(f"Removed count: {len(removed)}/{len(prev_symbols)}")

    def normalize(s):
        return s.split(":")[0]

    removed_normalized = {normalize(s) for s in removed}
    added_normalized = {normalize(s) for s in added}

    format_changes = removed_normalized.intersection(added_normalized)

    if format_changes:
        # Use next(iter(...)) to avoid RUF015
        sample_change = next(iter(format_changes))
        errors.append(
            f"Drift Error: Pair format changed for {len(format_changes)} pairs "
            f"(e.g., {sample_change})"
        )
        drift_stats["format_changes"] = list(format_changes)

    return drift_stats


def generate_report(path, status, current_path, symbols_count, errors, drift_stats):
    try:
        with Path(path).open("w") as f:
            f.write("# Markets Schema Validation Report\n")
            f.write(f"Date: {datetime.now(UTC).isoformat()}\n")
            f.write(f"Status: {status}\n")
            f.write(f"File: {current_path}\n")
            f.write(f"Eligible Markets count: {symbols_count}\n")

            if drift_stats:
                f.write("## Drift Statistics\n")
                f.write(f"- Previous Whitelist Count: {drift_stats['total_prev']}\n")
                f.write(f"- Candidate Whitelist Count: {drift_stats['total_cand']}\n")
                f.write(f"- Added: {drift_stats['added_count']}\n")
                f.write(f"- Removed: {drift_stats['removed_count']}\n")
                f.write(f"- Removal Ratio: {drift_stats['ratio']:.2f}\n")

                if drift_stats.get("format_changes"):
                    f.write(f"- Format Changes Detected: {len(drift_stats['format_changes'])}\n")
                    for fc in drift_stats["format_changes"][:10]:
                        f.write(f"  - {fc}\n")

                if drift_stats["removed_samples"]:
                    samples = ", ".join(drift_stats["removed_samples"])
                    f.write(f"- Removed Samples: {samples}\n")

            if errors:
                f.write("## Errors\n")
                for e in errors:
                    f.write(f"- {e}\n")
        print(f"Report written to {path}")
    except Exception as e:
        warn(f"Could not write report: {e}")


def check_env_sanity(data, expected_env):
    # Check for metadata if available
    # Usually Freqtrade list-markets output is a list of markets.
    # If it's a dict, it might contain info.
    # If raw list, we can't check exchange metadata easily.
    # We warn if we can't verify.

    verified = False

    # Placeholder for logic to detect environment from market data
    # E.g. check for specific testnet pairs or URL references in 'info'
    if isinstance(data, list) and len(data) > 0:
        # sample = data[0]
        # Delta testnet pairs might have same names as prod.
        # Check 'info' dict if available
        # info = sample.get("info", {})
        # This depends on what CCXT returns.
        pass

    if not verified:
        warn(
            f"Could not verify market dump matches DELTA_ENV={expected_env} "
            "(No metadata found). Proceeding with caution."
        )


def main():
    parser = argparse.ArgumentParser(description="Validate markets schema and whitelist drift.")
    parser.add_argument("--markets", required=True, help="Path to the markets JSON file")
    parser.add_argument(
        "--candidate-whitelist", required=False, help="Path to the candidate whitelist JSON file"
    )
    parser.add_argument(
        "--prev-whitelist", required=False, help="Path to the previous whitelist JSON file"
    )
    parser.add_argument("--env", required=False, default="india_prod", help="Expected environment")
    parser.add_argument(
        "--out-report",
        required=False,
        default="user_data/reports/markets_schema_report.md",
        help="Output path for the report",
    )

    args = parser.parse_args()

    current_path = args.markets
    candidate_path = args.candidate_whitelist
    prev_path = args.prev_whitelist
    expected_env = args.env

    print(f"Validating {current_path}...")

    try:
        with Path(current_path).open() as f:
            data = json.load(f)
    except Exception as e:
        fail(f"Invalid JSON: {e}")

    # Standardize data structure
    if isinstance(data, dict) and "markets" in data:
        data = data["markets"]
    elif not isinstance(data, list):
        fail("Root must be a list or dict with 'markets'")

    check_env_sanity(data, expected_env)

    errors, symbols = validate_schema(data)
    drift_stats = None

    if candidate_path:
        drift_stats = validate_drift(candidate_path, prev_path, errors)

    status = "FAIL" if errors else "PASS"

    generate_report(args.out_report, status, current_path, len(symbols), errors, drift_stats)

    if errors:
        print("Validation Failed:")
        for err in errors[:10]:
            print(f"  - {err}")
        if len(errors) > 10:
            print(f"  ... and {len(errors) - 10} more.")
        sys.exit(2)

    print(f"Validation PASS. Found {len(symbols)} eligible symbols.")


if __name__ == "__main__":
    main()
