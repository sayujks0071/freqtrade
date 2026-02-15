#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path


# Configuration from Environment
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


def is_eligible(market):
    """
    Determines if a market is eligible for the whitelist based on FILTER_MODE.
    This logic mirrors tools/generate_whitelist.py.
    """
    symbol = market.get("symbol", "")
    if not market.get("active", True):
        return False

    regex = re.compile(ALLOWLIST_REGEX)

    if FILTER_MODE == "perps_usdt":
        # Check if quote is USDT and it's a perp (symbol contains /USDT:USDT)
        return "/USDT:USDT" in symbol
    elif FILTER_MODE == "all_futures":
        # Assuming all markets in the dump are futures or checking type
        # Ideally we check type but generate_whitelist.py just accepts all
        return True
    elif FILTER_MODE == "allowlist_regex":
        return bool(regex.match(symbol))
    else:
        # Default to perps_usdt
        return "/USDT:USDT" in symbol


def validate_market_structure(i, m, errors):
    # Required fields
    for f in REQUIRED_FIELDS:
        if f not in m:
            errors.append(f"Item {i} missing field '{f}'")

    symbol = m.get("symbol", "")
    if not symbol:
        errors.append(f"Item {i} has empty symbol")
        return None

    # Check for at least one type indicator if available
    # Freqtrade dump usually has 'type', 'contract', 'future', 'linear', 'swap'
    # Requirement: active (bool or truthy)
    # active is checked in REQUIRED_FIELDS

    # Requirement: type / contract / future/perp indicator (at least one)
    type_indicators = ["type", "contract", "future", "linear", "swap", "spot"]
    has_type = any(k in m for k in type_indicators)
    # Also check if 'info' has type info? usually top level in freqtrade dump
    if not has_type:
        # Some dumps might not have explicit type field if it's a list of symbols?
        # But we validated it's a dict with keys.
        # If it is a list of dicts from ccxt, it should have 'type'.
        errors.append(f"Item {i} ({symbol}) missing type/contract indicator")

    return symbol


def validate_symbol_format(symbol, errors):
    # Symbol format: BASE/QUOTE:SETTLE for futures usually
    # Reject whitespace/lowercase
    if re.search(r"\s", symbol):
        errors.append(f"Symbol '{symbol}' contains whitespace")
    if symbol != symbol.upper():
        errors.append(f"Symbol '{symbol}' is not uppercase")

    # Strict check for futures format (must have settle delimiter) if implicit futures mode
    # If FILTER_MODE is perps_usdt or all_futures, we expect futures format
    if FILTER_MODE in ["perps_usdt", "all_futures"]:
        if ":" not in symbol:
            errors.append(f"Symbol '{symbol}' missing settle delimiter (:)")
        else:
            # Check for BASE/QUOTE:SETTLE structure
            parts = symbol.split(":")
            if len(parts) != 2:
                errors.append(f"Symbol '{symbol}' has invalid format (expected BASE/QUOTE:SETTLE)")
            elif "/" not in parts[0]:
                errors.append(f"Symbol '{symbol}' missing base/quote delimiter (/)")


def validate_numeric_fields(m, symbol, errors):
    # Check volume and limits
    # Reject markets with clearly invalid numeric fields (NaN, negative, absurdly huge)
    # Common numeric fields: 'spot', 'future', 'delivery', 'open', 'close', 'high', 'low', 'volume'
    # Freqtrade list-markets dump might be lean.
    # If it has 'info' dict, check inside? Or top level.
    # We check top level fields if they exist and are numbers.

    numeric_fields = ["volume", "quoteVolume", "price", "contractSize"]
    for f in numeric_fields:
        if f in m:
            val = m[f]
            if isinstance(val, (int, float)):
                if val < 0:
                    errors.append(f"Market {symbol} has negative {f}: {val}")
                # complex NaN check? json load handles standard numbers.
                # If it was NaN in JSON, python json.load might make it nan (float).
                # import math; math.isnan(val)
                import math

                if math.isnan(val):
                    errors.append(f"Market {symbol} has NaN {f}")
            elif val is None:
                # None might be acceptable? Requirement says "Reject ... invalid numeric fields".
                # If volume is None, it's not numeric.
                pass

    # Strict volume check
    if "volume" in m:
        vol = m.get("volume")
        if vol is not None and isinstance(vol, (int, float)) and vol < 1000 and STRICT_VOLUME:
            errors.append(f"Low volume for {symbol}: {vol}")


def validate_drift(candidate_symbols, prev_whitelist_path):
    prev_path_obj = Path(prev_whitelist_path)
    if not prev_whitelist_path or not prev_path_obj.exists():
        print("No previous whitelist found. Skipping drift check.")
        return [], [], 0.0

    try:
        with prev_path_obj.open() as f:
            prev_data = json.load(f)

        # Handle Freqtrade whitelist format: {"exchange": {"pair_whitelist": [...]}}
        # or list of strings
        if isinstance(prev_data, dict) and "exchange" in prev_data:
            prev_symbols = set(prev_data["exchange"].get("pair_whitelist", []))
        elif isinstance(prev_data, list):
            prev_symbols = set(prev_data)
        else:
            warn("Previous whitelist format unrecognized. Skipping drift check.")
            return [], [], 0.0
    except Exception as e:
        warn(f"Could not read previous whitelist: {e}")
        return [], [], 0.0

    removed = prev_symbols - candidate_symbols
    added = candidate_symbols - prev_symbols

    # Calculate removal ratio based on previous size
    removal_ratio = len(removed) / len(prev_symbols) if len(prev_symbols) > 0 else 0.0

    print(f"Drift stats: +{len(added)} / -{len(removed)} (Ratio: {removal_ratio:.2f})")

    return list(added), list(removed), removal_ratio


def write_report(path, report_content):
    try:
        with Path(path).open("w") as f:
            f.write(report_content)
        print(f"Report written to {path}")
    except Exception as e:
        warn(f"Could not write report: {e}")


def load_markets(markets_path):
    try:
        with Path(markets_path).open() as f:
            data = json.load(f)
    except Exception as e:
        fail(f"Invalid JSON: {e}")

    # Handle different dump formats
    if isinstance(data, list):
        markets_list = data
    elif isinstance(data, dict) and "markets" in data:
        markets_list = data["markets"]
    elif isinstance(data, dict):
        # Maybe dict of symbol -> market?
        # CCXT dump often uses symbol keys
        # If keys look like symbols (contain /), treat values as markets
        first_key = next(iter(data)) if data else ""
        if "/" in first_key:
            markets_list = list(data.values())
        else:
            # Fallback
            markets_list = [data]  # Unexpected
    else:
        markets_list = []

    if not isinstance(markets_list, list):
        fail("Could not parse markets list from JSON")

    return markets_list


def validate_markets(markets_list):
    candidate_symbols = set()
    eligible_count = 0
    errors = []

    # Validation C & D
    for i, m in enumerate(markets_list):
        if not isinstance(m, dict):
            errors.append(f"Item {i} is not a dictionary")
            continue

        # We'll do a basic structure check first to get symbol
        symbol = m.get("symbol")
        if not symbol:
            # If symbol missing, we can't check eligibility easily,
            # but we should report it if it's supposed to be a market
            # But maybe we only care about eligible ones?
            # Requirement A: "Non-empty markets count". We checked that.
            # Requirement C: "For each market that will be eligible..."
            # If symbol is missing, it can't be eligible.
            continue

        if is_eligible(m):
            eligible_count += 1

            # Now strict checks for eligible markets
            validated_symbol = validate_market_structure(i, m, errors)
            if validated_symbol:
                validate_symbol_format(validated_symbol, errors)
                validate_numeric_fields(m, validated_symbol, errors)

                if validated_symbol in candidate_symbols:
                    errors.append(f"Duplicate symbol '{validated_symbol}'")
                candidate_symbols.add(validated_symbol)

    return candidate_symbols, eligible_count, errors


def generate_report_content(args, markets_list, eligible_count, candidate_symbols,
                            added, removed, removal_ratio, errors, status):
    report_lines = [
        "# Markets Schema Validation Report",
        f"Date: {datetime.now(UTC).isoformat()}",
        f"Status: {status}",
        f"Environment: {args.env}",
        f"Total Markets: {len(markets_list)}",
        f"Eligible Markets: {eligible_count}",
        f"Candidate Whitelist Size: {len(candidate_symbols)}",
        f"File: {args.markets}",
        "",
        "## Drift Analysis",
        f"Previous Whitelist: {args.prev_whitelist}",
        f"Added: {len(added)}",
        f"Removed: {len(removed)}",
        f"Removal Ratio: {removal_ratio:.2%}",
        f"Max Removal Ratio: {MAX_REMOVAL_RATIO:.2%}",
    ]

    if removed:
        report_lines.append("\n### Removed Pairs")
        report_lines.extend([f"- {s}" for s in sorted(removed)[:20]])
        if len(removed) > 20:
            report_lines.append(f"...and {len(removed) - 20} more")

    if added:
        report_lines.append("\n### Added Pairs")
        report_lines.extend([f"- {s}" for s in sorted(added)[:20]])
        if len(added) > 20:
            report_lines.append(f"...and {len(added) - 20} more")

    if errors:
        report_lines.append("\n## Validation Errors")
        report_lines.extend([f"- {e}" for e in errors[:50]])  # Limit errors
        if len(errors) > 50:
            report_lines.append(f"...and {len(errors) - 50} more")

    return "\n".join(report_lines)


def main():
    parser = argparse.ArgumentParser(description="Validate market schema and drift.")
    parser.add_argument("--markets", required=True, help="Path to markets JSON dump")
    parser.add_argument("--prev-whitelist", help="Path to previous whitelist JSON")
    parser.add_argument("--env", help="Delta environment (e.g. india_prod)")
    parser.add_argument("--out-report", required=True, help="Path to output Markdown report")

    args = parser.parse_args()

    print(f"Validating {args.markets}...")

    markets_list = load_markets(args.markets)

    # Validation A & B
    if len(markets_list) < MIN_MARKETS:
        fail(f"Market count {len(markets_list)} < MIN_MARKETS ({MIN_MARKETS})")

    candidate_symbols, eligible_count, errors = validate_markets(markets_list)

    # Validation F: Drift
    added, removed, removal_ratio = validate_drift(candidate_symbols, args.prev_whitelist)

    if removal_ratio > MAX_REMOVAL_RATIO:
        errors.append(
            f"Large delist drift: {removal_ratio:.2%} > "
            f"MAX_REMOVAL_RATIO ({MAX_REMOVAL_RATIO:.2%})"
        )

    # Generate Report
    status = "PASS" if not errors else "FAIL"
    report_content = generate_report_content(
        args, markets_list, eligible_count, candidate_symbols,
        added, removed, removal_ratio, errors, status
    )

    write_report(args.out_report, report_content)

    if errors:
        fail(f"Validation failed with {len(errors)} errors. See report at {args.out_report}")

    print("VALIDATION PASS")


if __name__ == "__main__":
    main()
