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


def parse_args():
    parser = argparse.ArgumentParser(
        description="Validate Delta markets schema and whitelist drift."
    )
    parser.add_argument("--markets", required=True, help="Path to markets JSON file")
    parser.add_argument(
        "--env", default="india_prod", help="Delta Environment (india_prod, global_prod)"
    )
    parser.add_argument("--prev-whitelist", help="Path to previous whitelist JSON file")
    parser.add_argument(
        "--out-report",
        default="user_data/reports/markets_schema_report.md",
        help="Path to output report",
    )
    return parser.parse_args()


def validate_market_structure(i, m, errors):
    # Required fields
    for f in REQUIRED_FIELDS:
        if f not in m:
            errors.append(f"Item {i} missing field '{f}'")

    # At least one type indicator
    if not any(k in m for k in ["type", "contract", "future", "perp", "spot"]):
        errors.append(f"Item {i} missing type indicator (type/contract/future/perp)")

    symbol = m.get("symbol", "")
    if not symbol:
        errors.append(f"Item {i} has empty symbol")
        return None

    # Type check base/quote are strings
    if not isinstance(m.get("base"), str):
        errors.append(f"Item {i} base is not a string")
    if not isinstance(m.get("quote"), str):
        errors.append(f"Item {i} quote is not a string")

    return symbol


def validate_symbol_format(symbol, errors):
    # Symbol format: BASE/QUOTE:SETTLE for futures usually
    # Reject whitespace/lowercase
    if re.search(r"\s", symbol):
        errors.append(f"Symbol '{symbol}' contains whitespace")
    if symbol != symbol.upper():
        errors.append(f"Symbol '{symbol}' is not uppercase")

    # Strict check for futures format (must have settle currency)
    # The requirement says: "Must match futures style: BASE/QUOTE:SETTLE ...
    # OR a consistent CCXT format"
    if FILTER_MODE in ["perps_usdt", "all_futures"]:
        if ":" not in symbol:
            errors.append(
                f"Symbol '{symbol}' missing settle delimiter (:) required for {FILTER_MODE}"
            )


def check_volume_field(m, symbol, key, errors):
    if key in m and m[key] is not None:
        try:
            val = float(m[key])
            if val < 0:
                errors.append(f"{symbol}: Negative {key} {val}")
            # Check for NaN/Inf
            if val != val or val == float("inf"):
                errors.append(f"{symbol}: Invalid {key} {val}")
        except ValueError:
            errors.append(f"{symbol}: Non-numeric {key} {m[key]}")


def check_low_volume(m, symbol, errors):
    vol = m.get("quoteVolume", m.get("volume"))
    if vol is not None:
        try:
            val = float(vol)
            if val < 1000:
                msg = f"{symbol}: Low volume ({val}) < 1000"
                if STRICT_VOLUME:
                    errors.append(msg + " (STRICT_VOLUME=true)")
                else:
                    warn(msg)
        except (ValueError, TypeError):
            # Ignore invalid volume format here as it's likely handled by the loop above
            # or isn't critical enough to crash
            pass
        except Exception as e:
            warn(f"Unexpected error checking volume for {symbol}: {e}")


def validate_volume_limits(m, symbol, errors):
    # Check for clearly invalid numeric fields
    # numeric fields to check: volume, precision, limits

    # Volume
    # Freqtrade dump usually puts quoteVolume in 'quoteVolume' or just 'volume'
    # depending on exchange. We check standard ccxt fields if present
    for key in ["volume", "quoteVolume"]:
        check_volume_field(m, symbol, key, errors)

    # Optionally filter out near-zero volume markets if volume is available
    check_low_volume(m, symbol, errors)


def validate_environment_sanity(data, env, errors):
    # Confirm the dump corresponds to the intended DELTA_ENV
    sample_market = next((m for m in data if "info" in m), None)
    if sample_market:
        info = sample_market["info"]
        # If it's Delta, it should have specific fields.
        if "product_specs" in info or "contract_type" in info or "quoting_asset" in info:
            pass  # Looks like delta
        else:
            warn(
                "Market 'info' does not look like Delta Exchange data. Is this the right exchange?"
            )
    else:
        warn("No 'info' field found in markets. Cannot verify exchange identity.")


def get_candidate_whitelist(markets):
    # Duplicate logic from tools/generate_whitelist.py
    whitelist = []
    regex = re.compile(ALLOWLIST_REGEX)

    for m in markets:
        symbol = m["symbol"]

        # Basic active check
        if not m.get("active", True):
            continue

        # Filter logic
        if FILTER_MODE == "perps_usdt":
            if symbol.endswith("/USDT:USDT"):
                whitelist.append(symbol)
        elif FILTER_MODE == "all_futures":
            whitelist.append(symbol)
        elif FILTER_MODE == "allowlist_regex":
            if regex.match(symbol):
                whitelist.append(symbol)
        else:
            # Default to perps_usdt
            if symbol.endswith("/USDT:USDT"):
                whitelist.append(symbol)

    return sorted(list(set(whitelist)))


def load_previous_whitelist(path):
    try:
        with Path(path).open() as f:
            prev_data = json.load(f)

        if (
            isinstance(prev_data, dict)
            and "exchange" in prev_data
            and "pair_whitelist" in prev_data["exchange"]
        ):
            return set(prev_data["exchange"]["pair_whitelist"])
        elif isinstance(prev_data, list):
            return set(prev_data)
        else:
            warn("Previous whitelist format unrecognized. Skipping drift check.")
            return None
    except Exception as e:
        warn(f"Could not read previous whitelist: {e}")
        return None


def validate_drift(candidate_whitelist, prev_whitelist_path, errors):
    prev_path_obj = Path(prev_whitelist_path)
    if not prev_whitelist_path or not prev_path_obj.exists():
        print("No previous whitelist found. Skipping drift check.")
        return

    prev_symbols = load_previous_whitelist(prev_whitelist_path)
    if prev_symbols is None:
        return

    current_symbols = set(candidate_whitelist)
    removed = prev_symbols - current_symbols
    added = current_symbols - prev_symbols

    len_prev = len(prev_symbols)
    removal_ratio = len(removed) / len_prev if len_prev > 0 else 0.0

    print(f"Drift stats: +{len(added)} / -{len(removed)} (Ratio: {removal_ratio:.2f})")

    if removal_ratio > MAX_REMOVAL_RATIO:
        errors.append(
            f"Large delist drift — manual review required. "
            f"Removal ratio {removal_ratio:.2f} > MAX_REMOVAL_RATIO ({MAX_REMOVAL_RATIO})."
        )

    # Check for pair format changes
    check_format_changes(prev_symbols, current_symbols, errors)


def check_format_changes(prev_symbols, current_symbols, errors):
    # Identify pairs by Base/Quote (e.g. "BTC/USDT" from "BTC/USDT:USDT")
    # If we find the same Base/Quote with a different full symbol, flag it.

    def get_pair_key(s):
        if ":" in s:
            return s.split(":")[0]
        return s

    prev_map = {get_pair_key(s): s for s in prev_symbols}
    curr_map = {get_pair_key(s): s for s in current_symbols}

    format_changes = []
    for k, prev_s in prev_map.items():
        if k in curr_map:
            curr_s = curr_map[k]
            if prev_s != curr_s:
                format_changes.append(f"{prev_s} -> {curr_s}")

    if format_changes:
        errors.append(
            f"Pair format changed for {len(format_changes)} pairs: "
            f"{', '.join(format_changes[:5])}..."
        )


def write_report(path, report_content):
    try:
        with Path(path).open("w") as f:
            f.write(report_content)
        print(f"Report written to {path}")
    except Exception as e:
        warn(f"Could not write report: {e}")


def generate_report(args, data, candidate_whitelist, errors):
    status = "PASS" if not errors else "FAIL"
    report_content = f"""# Markets Schema Validation Report
Date: {datetime.now(UTC).isoformat()}
Status: {status}
Markets File: {args.markets}
Total Markets: {len(data)}
Eligible Markets: {len(candidate_whitelist)}
Previous Whitelist: {args.prev_whitelist or "None"}

## Errors
"""
    if errors:
        for e in errors:
            report_content += f"- {e}\n"
    else:
        report_content += "No errors found.\n"
    return report_content, status


def load_markets(path):
    try:
        with Path(path).open() as f:
            data = json.load(f)
    except Exception as e:
        fail(f"Invalid JSON in markets file: {e}")

    # Handle Freqtrade dump format (list or dict with 'markets')
    if isinstance(data, dict) and "markets" in data:
        data = data["markets"]
    elif not isinstance(data, list):
        fail("Markets data must be a list or a dict with 'markets' key")

    # A) Min Markets
    if len(data) < MIN_MARKETS:
        fail(f"Market count {len(data)} < MIN_MARKETS ({MIN_MARKETS})")

    return data


def perform_validation_loop(data, errors):
    symbols = set()
    regex = re.compile(ALLOWLIST_REGEX)

    for i, m in enumerate(data):
        # C) Schema & D) Volume/Limits
        symbol = validate_market_structure(i, m, errors)
        if not symbol:
            continue

        # Check uniqueness
        if symbol.lower() in symbols:
            errors.append(f"Duplicate symbol '{symbol}' (case-insensitive)")
        symbols.add(symbol.lower())

        # Check eligibility
        is_eligible = False
        if FILTER_MODE == "perps_usdt" and symbol.endswith("/USDT:USDT"):
            is_eligible = True
        elif FILTER_MODE == "all_futures":
            is_eligible = True
        elif FILTER_MODE == "allowlist_regex":
            if regex.match(symbol):
                is_eligible = True
        else:
            # Default to perps_usdt
            if symbol.endswith("/USDT:USDT"):
                is_eligible = True

        if is_eligible:
            validate_symbol_format(symbol, errors)
            validate_volume_limits(m, symbol, errors)


def main():
    args = parse_args()
    print(f"Validating {args.markets} for env {args.env}...")

    # Load markets
    data = load_markets(args.markets)

    errors = []

    # E) Environment Sanity
    validate_environment_sanity(data, args.env, errors)

    # Validation loop
    perform_validation_loop(data, errors)

    # F) Drift Safety Gate
    candidate_whitelist = get_candidate_whitelist(data)

    # Check if candidate whitelist is empty
    if not candidate_whitelist:
        errors.append(
            f"Candidate whitelist is empty! Check FILTER_MODE ({FILTER_MODE}) and markets dump."
        )

    if args.prev_whitelist:
        validate_drift(candidate_whitelist, args.prev_whitelist, errors)

    # Report generation
    report_content, _ = generate_report(args, data, candidate_whitelist, errors)
    write_report(args.out_report, report_content)

    if errors:
        print("VALIDATION FAILED")
        sys.exit(2)
    else:
        print("VALIDATION PASS")
        sys.exit(0)


if __name__ == "__main__":
    main()
