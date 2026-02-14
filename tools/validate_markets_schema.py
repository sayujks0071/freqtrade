#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone


# Load environment variables or defaults
MIN_MARKETS = int(os.getenv("MIN_MARKETS", 20))
MAX_REMOVAL_RATIO = float(os.getenv("MAX_REMOVAL_RATIO", 0.25))
STRICT_VOLUME = os.getenv("STRICT_VOLUME", "false").lower() == "true"
FILTER_MODE = os.getenv("FILTER_MODE", "perps_usdt")
ALLOWLIST_REGEX = os.getenv("ALLOWLIST_REGEX", ".*")


def load_json(filepath):
    try:
        with open(filepath, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading {filepath}: {e}")
        return None


def is_eligible(market):
    """
    Check if a market is eligible based on FILTER_MODE and schema.
    """
    symbol = market.get("symbol", "")
    if not symbol:
        return False

    # Basic schema check
    required_keys = ["symbol", "base", "quote", "active"]
    if not all(k in market for k in required_keys):
        return False

    if not market["active"]:
        return False

    # Filter logic
    if FILTER_MODE == "perps_usdt":
        # Delta futures often have format BASE/QUOTE:SETTLE or similar.
        # Ensure it's a USDT perp.
        # Assuming CCXT structure.
        if market.get("linear") and market.get("quote") == "USDT":
            return True
        # Fallback to checking symbol string if 'linear' not present (some ccxt versions)
        if "/USDT:USDT" in symbol:
            return True
        return False
    elif FILTER_MODE == "all_futures":
        return (
            market.get("future", False)
            or market.get("swap", False)
            or market.get("contract", False)
        )
    elif FILTER_MODE == "allowlist_regex":
        return re.match(ALLOWLIST_REGEX, symbol) is not None

    return False


def validate_schema_rules(markets):
    errors = []
    valid_markets = []

    for m in markets:
        if not is_eligible(m):
            continue

        symbol = m.get("symbol", "UNKNOWN")

        # Rule: Symbol format consistency
        if " " in symbol:
            errors.append(f"Symbol {symbol} contains whitespace")
            continue

        if symbol != symbol.upper():
            errors.append(f"Symbol {symbol} is not uppercase")
            continue

        # Futures format check: BASE/QUOTE:SETTLE
        if ":" not in symbol:
            # This might be valid for spot, but for futures on Delta via CCXT it usually has :
            # If strictly futures mode, warn or fail.
            if FILTER_MODE in ["perps_usdt", "all_futures"]:
                errors.append(f"Symbol {symbol} missing settle delimiter ':'")
                continue

        valid_markets.append(m["symbol"])

    return valid_markets, errors


def main():
    parser = argparse.ArgumentParser(description="Validate market dump and whitelist drift.")
    parser.add_argument("--markets", required=True, help="Path to markets JSON dump")
    parser.add_argument(
        "--candidate-whitelist",
        required=False,
        help="Path to candidate whitelist JSON (output of this script if valid)",
    )
    parser.add_argument(
        "--prev-whitelist", required=False, help="Path to previous whitelist JSON for drift check"
    )
    parser.add_argument("--env", required=True, help="Environment name (e.g. india_prod)")
    parser.add_argument("--out-report", required=True, help="Path to output markdown report")

    args = parser.parse_args()

    report_lines = [f"# Market Validation Report - {args.env}"]
    report_lines.append(f"Date: {datetime.now(timezone.utc).isoformat()}")
    report_lines.append(f"Filter Mode: {FILTER_MODE}")

    # 1. Load Markets
    data = load_json(args.markets)
    if not data:
        print("Failed to load markets.")
        sys.exit(2)

    if isinstance(data, list):
        market_list = data
    elif isinstance(data, dict) and "markets" in data:
        market_list = data["markets"]  # Depending on structure
    else:
        # ccxt structure might be dict of symbol->market
        market_list = list(data.values()) if isinstance(data, dict) else []

    if not market_list:
        print("Market list is empty.")
        sys.exit(2)

    # 2. Schema Validation & Eligibility
    valid_symbols, errors = validate_schema_rules(market_list)

    report_lines.append(f"## Schema Validation")
    report_lines.append(f"- Total Markets in Dump: {len(market_list)}")
    report_lines.append(f"- Eligible Markets: {len(valid_symbols)}")
    report_lines.append(f"- Schema Errors: {len(errors)}")

    if len(errors) > 0:
        report_lines.append("\n### Sample Errors")
        for e in errors[:10]:
            report_lines.append(f"- {e}")
        if len(errors) > 10:
            report_lines.append(f"- ... and {len(errors) - 10} more")

    if len(valid_symbols) < MIN_MARKETS:
        msg = f"FAIL: Eligible markets ({len(valid_symbols)}) < MIN_MARKETS ({MIN_MARKETS})"
        print(msg)
        report_lines.append(f"\n**{msg}**")
        with open(args.out_report, "w") as f:
            f.write("\n".join(report_lines))
        sys.exit(2)

    # 3. Drift Check
    drift_status = "PASS"
    if args.prev_whitelist and os.path.exists(args.prev_whitelist):
        prev_data = load_json(args.prev_whitelist)
        if prev_data:
            prev_symbols = set(prev_data.get("exchange", {}).get("pair_whitelist", []))
            current_symbols = set(valid_symbols)

            removed = prev_symbols - current_symbols
            added = current_symbols - prev_symbols

            removal_ratio = len(removed) / len(prev_symbols) if len(prev_symbols) > 0 else 0.0

            report_lines.append(f"\n## Drift Check")
            report_lines.append(f"- Previous Whitelist Size: {len(prev_symbols)}")
            report_lines.append(f"- Removed: {len(removed)} ({removal_ratio:.2%})")
            report_lines.append(f"- Added: {len(added)}")

            if removal_ratio > MAX_REMOVAL_RATIO:
                drift_status = "FAIL"
                msg = f"FAIL: Removal ratio {removal_ratio:.2%} > MAX_REMOVAL_RATIO {MAX_REMOVAL_RATIO:.2%}"
                print(msg)
                report_lines.append(f"\n**{msg}**")
            else:
                report_lines.append(f"\n**Drift Check PASSED**")

            if removed:
                report_lines.append("\n### Removed Pairs")
                report_lines.append(
                    ", ".join(list(removed)[:20]) + ("..." if len(removed) > 20 else "")
                )
            if added:
                report_lines.append("\n### Added Pairs")
                report_lines.append(
                    ", ".join(list(added)[:20]) + ("..." if len(added) > 20 else "")
                )

    # 4. Generate Output Whitelist (if requested)
    if args.candidate_whitelist and drift_status == "PASS":
        out_data = {"exchange": {"pair_whitelist": sorted(list(valid_symbols))}}
        with open(args.candidate_whitelist, "w") as f:
            json.dump(out_data, f, indent=4)
        print(f"Generated whitelist with {len(valid_symbols)} pairs.")

    # Write Report
    with open(args.out_report, "w") as f:
        f.write("\n".join(report_lines))

    if drift_status == "FAIL":
        sys.exit(2)

    print("Validation PASSED.")
    sys.exit(0)


if __name__ == "__main__":
    main()
