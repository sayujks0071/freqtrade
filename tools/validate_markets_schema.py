#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# Try to import generate_whitelist from the same directory
try:
    import generate_whitelist
except ImportError:
    # If running from root without tools in path, might fail if not handled
    sys.path.append(str(Path(__file__).parent))
    import generate_whitelist

# Configuration
MIN_MARKETS = int(os.environ.get("MIN_MARKETS", 20))
MAX_REMOVAL_RATIO = float(os.environ.get("MAX_REMOVAL_RATIO", 0.25))
STRICT_VOLUME = os.environ.get("STRICT_VOLUME", "false").lower() == "true"
FILTER_MODE = os.environ.get("FILTER_MODE", "perps_usdt")
ALLOWLIST_REGEX = os.environ.get("ALLOWLIST_REGEX", ".*")

REQUIRED_FIELDS = ["symbol", "base", "quote", "active"]


def fail(message, report_path=None, report_content=None):
    print(f"FAIL: {message}")
    if report_path and report_content:
        try:
            write_report(report_path, report_content + f"\n\n## FAILURE REASON\n{message}")
        except Exception as e:
            print(f"Could not write report: {e}")
    sys.exit(2)


def warn(message):
    print(f"WARN: {message}")


def write_report(path, message):
    path_obj = Path(path)
    path_obj.parent.mkdir(parents=True, exist_ok=True)
    with path_obj.open("w") as f:
        f.write(message)


def validate_market_structure(i, m, errors):
    # Required fields
    for f in REQUIRED_FIELDS:
        if f not in m:
            errors.append(f"Item {i} missing field '{f}'")

    symbol = m.get("symbol", "")
    if not symbol:
        errors.append(f"Item {i} has empty symbol")
        return None

    # Requirement: "type / contract / future/perp indicator (at least one)"
    has_type = False
    for k in ["type", "contract", "future", "linear", "swap"]:
        if k in m:
            has_type = True
            break

    if not has_type:
         errors.append(f"Item {i} ({symbol}) missing type indicator")

    return symbol


def validate_symbol_format(symbol, errors, is_futures=True):
    # Requirement: Must match futures style: BASE/QUOTE:SETTLE

    if re.search(r"\s", symbol):
        errors.append(f"Symbol '{symbol}' contains whitespace")

    if symbol != symbol.upper():
         errors.append(f"Symbol '{symbol}' is not uppercase")

    if is_futures:
        if ":" not in symbol:
             errors.append(f"Symbol '{symbol}' missing settle delimiter (:) for futures")

        parts = symbol.split(":")
        if len(parts) != 2:
             errors.append(f"Symbol '{symbol}' has invalid structure (expected BASE/QUOTE:SETTLE)")
        elif "/" not in parts[0]:
             errors.append(f"Symbol '{symbol}' missing base/quote separator (/)")


def validate_numeric(m, symbol, errors):
    # Requirement D
    def check_val(val, name):
        if val is None: return
        if not isinstance(val, (int, float)): return
        if val < 0:
            errors.append(f"{symbol}: Negative {name} ({val})")
        if val != val: # NaN
            errors.append(f"{symbol}: NaN {name}")

    if "limits" in m and isinstance(m["limits"], dict):
        limits = m["limits"]
        for cat in ["amount", "price", "cost"]:
            if cat in limits and isinstance(limits[cat], dict):
                check_val(limits[cat].get("min"), f"limits.{cat}.min")
                check_val(limits[cat].get("max"), f"limits.{cat}.max")

    if STRICT_VOLUME:
        vol = m.get("volume")
        if vol is not None and isinstance(vol, (int, float)):
             if vol < 1000:
                  errors.append(f"Low volume for {symbol}: {vol} (STRICT_VOLUME=true)")


def load_markets(path):
    try:
        with Path(path).open() as f:
            data = json.load(f)
    except Exception as e:
        raise ValueError(f"Invalid JSON in markets file: {e}")

    markets_list = []
    if isinstance(data, list):
        markets_list = data
    elif isinstance(data, dict) and "markets" in data:
        markets_list = data["markets"]
    else:
        raise ValueError("Invalid structure: Top level must be list or dict with 'markets' key")

    return markets_list


def load_prev_whitelist(path):
    path_obj = Path(path)
    if not path_obj.exists():
        return None, "Previous Whitelist: None (First run?)"

    try:
        with path_obj.open() as f:
            pw_data = json.load(f)
            if isinstance(pw_data, dict) and "exchange" in pw_data:
                return pw_data["exchange"].get("pair_whitelist", []), None
            elif isinstance(pw_data, list):
                return pw_data, None
            else:
                 return [], "Previous Whitelist: Invalid format"
    except Exception as e:
        return [], f"Could not load previous whitelist: {e}"


def check_drift(candidate_whitelist, prev_whitelist):
    prev_set = set(prev_whitelist)
    curr_set = set(candidate_whitelist)

    removed = prev_set - curr_set
    added = curr_set - prev_set

    removal_ratio = 0.0
    if len(prev_set) > 0:
        removal_ratio = len(removed) / len(prev_set)

    return prev_set, curr_set, added, removed, removal_ratio


def main():
    parser = argparse.ArgumentParser(description="Validate markets schema and check for drift.")
    parser.add_argument("--markets", required=True, help="Path to markets.json")
    parser.add_argument("--env", required=True, help="Delta Environment (e.g. india_prod)")
    parser.add_argument("--prev-whitelist", required=True, help="Path to previous whitelist.json")
    parser.add_argument("--out-report", required=True, help="Path to output report markdown")

    args = parser.parse_args()

    print(f"Validating {args.markets} for env {args.env}...")

    report_lines = [
        f"# Markets Schema Validation Report",
        f"Date: {datetime.now(timezone.utc).isoformat()}",
        f"Environment: {args.env}",
        f"File: {args.markets}"
    ]

    try:
        markets_list = load_markets(args.markets)
    except ValueError as e:
        fail(str(e))

    if len(markets_list) < MIN_MARKETS:
        fail(f"Market count {len(markets_list)} < MIN_MARKETS ({MIN_MARKETS})", args.out_report, "\n".join(report_lines))

    errors = []
    symbols_seen = set()

    for i, m in enumerate(markets_list):
        symbol = validate_market_structure(i, m, errors)
        if not symbol: continue

        validate_symbol_format(symbol, errors, is_futures=True)

        if symbol.lower() in symbols_seen:
             errors.append(f"Duplicate symbol '{symbol}' (case-insensitive)")
        symbols_seen.add(symbol.lower())

        validate_numeric(m, symbol, errors)

    if errors:
        error_msg = "Schema errors:\n" + "\n".join(errors[:20])
        if len(errors) > 20: error_msg += f"\n... and {len(errors)-20} more."
        fail(error_msg, args.out_report, "\n".join(report_lines))

    report_lines.append(f"Total Markets: {len(markets_list)}")
    report_lines.append("Schema Validation: PASS")

    # Drift Check
    candidate_whitelist = generate_whitelist.filter_markets(
        markets_list,
        filter_mode=FILTER_MODE,
        allowlist_regex=ALLOWLIST_REGEX
    )

    report_lines.append(f"Candidate Whitelist Size: {len(candidate_whitelist)}")

    prev_whitelist, load_err = load_prev_whitelist(args.prev_whitelist)
    if load_err:
        report_lines.append(load_err)
    if prev_whitelist is None: # File didn't exist
        prev_whitelist = []

    prev_set, curr_set, added, removed, removal_ratio = check_drift(candidate_whitelist, prev_whitelist)

    report_lines.append(f"Drift Stats:")
    report_lines.append(f"- Previous Count: {len(prev_set)}")
    report_lines.append(f"- Current Count: {len(curr_set)}")
    report_lines.append(f"- Added: {len(added)}")
    report_lines.append(f"- Removed: {len(removed)}")
    report_lines.append(f"- Removal Ratio: {removal_ratio:.2f}")

    if removal_ratio > MAX_REMOVAL_RATIO:
        fail_msg = f"Large delist drift — manual review required. Removal ratio {removal_ratio:.2f} > {MAX_REMOVAL_RATIO}"
        fail(fail_msg, args.out_report, "\n".join(report_lines))

    report_lines.append("Status: PASS")

    write_report(args.out_report, "\n".join(report_lines))
    print("VALIDATION PASS")


if __name__ == "__main__":
    main()
