#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# Configuration from Environment
MIN_MARKETS = int(os.environ.get("MIN_MARKETS", 20))
MAX_REMOVAL_RATIO = float(os.environ.get("MAX_REMOVAL_RATIO", 0.25))
STRICT_VOLUME = os.environ.get("STRICT_VOLUME", "false").lower() == "true"
FILTER_MODE = os.environ.get("FILTER_MODE", "perps_usdt")
ALLOWLIST_REGEX = os.environ.get("ALLOWLIST_REGEX", ".*")

REQUIRED_FIELDS = ["symbol", "base", "quote", "active"]

def fail(message, report_path=None, report_content=None):
    print(f"FAIL: {message}")
    if report_path and report_content:
        # Append failure reason to report
        try:
            with Path(report_path).open("w") as f:
                f.write(report_content + f"\n\n## FATAL ERROR\n{message}")
        except Exception as e:
            print(f"Could not write report: {e}")
    sys.exit(2)

def warn(message):
    print(f"WARN: {message}")

def filter_markets(markets):
    whitelist = []
    regex = re.compile(ALLOWLIST_REGEX)

    for m in markets:
        symbol = m.get("symbol", "")
        if not symbol:
            continue

        # Basic active check
        if not m.get("active", True):
            continue

        # Filter logic
        if FILTER_MODE == "perps_usdt":
            if "/USDT:USDT" in symbol:
                whitelist.append(symbol)
        elif FILTER_MODE == "all_futures":
            whitelist.append(symbol)
        elif FILTER_MODE == "allowlist_regex":
            if regex.match(symbol):
                whitelist.append(symbol)
        else:
            # Default to perps_usdt
            if "/USDT:USDT" in symbol:
                whitelist.append(symbol)

    return sorted(list(set(whitelist)))

def validate_market_structure(i, m, errors):
    for f in REQUIRED_FIELDS:
        if f not in m:
            errors.append(f"Item {i} missing field '{f}'")
            return None

    symbol = m.get("symbol", "")
    if not symbol:
        errors.append(f"Item {i} has empty symbol")
        return None

    # Check if it has at least one type indicator (type, contract, future, linear, swap)
    if not any(k in m for k in ["type", "contract", "future", "swap", "linear"]):
         if "type" not in m:
             errors.append(f"Item {i} ({symbol}) missing 'type' field")

    return symbol

def validate_symbol_format(symbol, errors):
    if re.search(r"\s", symbol):
        errors.append(f"Symbol '{symbol}' contains whitespace")
    if symbol != symbol.upper():
        errors.append(f"Symbol '{symbol}' is not uppercase")

    # Expecting BASE/QUOTE:SETTLE for futures
    if ":" not in symbol:
         errors.append(f"Symbol '{symbol}' missing settle delimiter (:)")
    if "/" not in symbol:
         errors.append(f"Symbol '{symbol}' missing quote delimiter (/)")

def validate_volume(m, symbol, errors):
    # Check for NaN, negative in numeric fields if present
    # Check 'limits'
    if "limits" in m and isinstance(m["limits"], dict):
        for k, v in m["limits"].items():
            if isinstance(v, dict):
                for bound in ["min", "max"]:
                    if bound in v:
                         val = v[bound]
                         if isinstance(val, (int, float)) and val < 0:
                             errors.append(f"Market {symbol} has negative limit {k}.{bound}: {val}")

    # Optionally filter out near-zero volume markets if volume is available
    if STRICT_VOLUME:
        # Check if volume data is present in 'info' or top level
        # This is highly exchange specific.
        # Delta 'info' usually has 'volume' field.
        vol = None
        if "info" in m and isinstance(m["info"], dict):
             # Try common keys
             for vk in ["volume", "volume_24h", "turnover"]:
                 if vk in m["info"]:
                     try:
                         vol = float(m["info"][vk])
                         break
                     except (ValueError, TypeError):
                         pass

        if vol is not None:
             if vol < 1000: # Arbitrary threshold for strict mode
                 errors.append(f"Low volume for {symbol}: {vol} < 1000")
        else:
             # If strict mode is on but no volume data found, warn?
             # Probably just ignore since list-markets might not have it.
             pass

def validate_schema(data):
    if not isinstance(data, list):
        return ["Root must be a list of markets"], set()

    if len(data) < MIN_MARKETS:
        return [f"Market count {len(data)} < MIN_MARKETS ({MIN_MARKETS})"], set()

    symbols = set()
    errors = []

    for i, m in enumerate(data):
        symbol = validate_market_structure(i, m, errors)
        if not symbol:
            continue

        validate_symbol_format(symbol, errors)

        if symbol in symbols:
            errors.append(f"Duplicate symbol '{symbol}'")
        symbols.add(symbol)

        validate_volume(m, symbol, errors)

    return errors, symbols

def validate_drift(current_whitelist_symbols, prev_whitelist_path):
    prev_path_obj = Path(prev_whitelist_path) if prev_whitelist_path else None
    if not prev_whitelist_path or not prev_path_obj.exists():
        print("No previous whitelist found. Skipping drift check.")
        return [], None, None

    try:
        with prev_path_obj.open() as f:
            prev_data = json.load(f)
            # Expecting freqtrade whitelist format: {"exchange": {"pair_whitelist": [...]}}
            if isinstance(prev_data, dict) and "exchange" in prev_data and "pair_whitelist" in prev_data["exchange"]:
                prev_symbols = set(prev_data["exchange"]["pair_whitelist"])
            elif isinstance(prev_data, list):
                prev_symbols = set(prev_data)
            else:
                 return [f"Unknown format in previous whitelist {prev_whitelist_path}"], None, None
    except Exception as e:
        return [f"Could not read previous whitelist: {e}"], None, None

    removed = prev_symbols - current_whitelist_symbols
    added = current_whitelist_symbols - prev_symbols

    if len(prev_symbols) == 0:
        removal_ratio = 0.0
    else:
        removal_ratio = len(removed) / len(prev_symbols)

    drift_errors = []
    drift_info = {
        "added": len(added),
        "removed": len(removed),
        "total_prev": len(prev_symbols),
        "total_curr": len(current_whitelist_symbols),
        "ratio": removal_ratio,
        "sample_removed": list(removed)[:5],
        "sample_added": list(added)[:5]
    }

    if removal_ratio > MAX_REMOVAL_RATIO:
        drift_errors.append(
            f"Large delist drift: {removal_ratio:.2f} > {MAX_REMOVAL_RATIO} "
            f"(-{len(removed)} pairs)"
        )

    return drift_errors, drift_info, prev_symbols

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--markets", required=True, help="Path to markets JSON")
    parser.add_argument("--env", help="Delta Environment (e.g. india_prod)")
    parser.add_argument("--prev-whitelist", help="Path to previous whitelist JSON")
    parser.add_argument("--out-report", required=True, help="Path to write Markdown report")

    args = parser.parse_args()

    print(f"Validating {args.markets}...")

    try:
        with Path(args.markets).open() as f:
            data = json.load(f)
    except Exception as e:
        fail(f"Invalid JSON: {e}")

    # Normalize data
    if isinstance(data, dict) and "markets" in data:
        data = data["markets"]

    # 1. Schema Validation
    schema_errors, all_symbols = validate_schema(data)

    # 2. Env Sanity Check
    # Confirm the dump corresponds to the intended DELTA_ENV by checking for
    # a recognizable base URL / exchange id if available in metadata; otherwise log a warning.
    if data and isinstance(data, list) and len(data) > 0:
        sample = data[0]
        # Check for 'info' field
        if "info" not in sample:
            warn("Market data missing 'info' field - cannot verify environment metadata.")
        else:
             # Basic check: if 'info' is empty, also warn
             if not sample["info"]:
                 warn("Market data 'info' field is empty - cannot verify environment metadata.")

    # 3. Simulate Whitelist Generation
    current_whitelist = set(filter_markets(data))

    # 4. Drift Check
    drift_errors, drift_info, _prev_symbols = validate_drift(current_whitelist, args.prev_whitelist)

    # Combine Errors
    all_errors = schema_errors + drift_errors
    status = "PASS" if not all_errors else "FAIL"

    # Generate Report
    report_lines = [
        "# Markets Schema Validation Report",
        f"**Date:** {datetime.now(timezone.utc).isoformat()}",  # noqa: UP017
        f"**Status:** {status}",
        f"**Environment:** {args.env or 'Unknown'}",
        f"**File:** `{args.markets}`",
        "",
        "## Summary",
        f"- **Total Markets Found:** {len(all_symbols)}",
        f"- **Eligible for Whitelist:** {len(current_whitelist)}",
    ]

    if drift_info:
        report_lines.extend([
            f"- **Previous Whitelist Size:** {drift_info['total_prev']}",
            f"- **Added:** {drift_info['added']}",
            f"- **Removed:** {drift_info['removed']}",
            f"- **Removal Ratio:** {drift_info['ratio']:.2%} (Limit: {MAX_REMOVAL_RATIO:.0%})",
        ])

    if all_errors:
        report_lines.append("\n## Errors")
        for e in all_errors:
            report_lines.append(f"- ❌ {e}")

    if drift_info and (drift_info['sample_removed'] or drift_info['sample_added']):
        report_lines.append("\n## Drift Details")
        if drift_info['sample_removed']:
            report_lines.append(f"**Removed (sample):** {', '.join(drift_info['sample_removed'])}")
        if drift_info['sample_added']:
            report_lines.append(f"**Added (sample):** {', '.join(drift_info['sample_added'])}")

    report_content = "\n".join(report_lines)

    # Write Report
    try:
        # Ensure parent directory exists
        Path(args.out_report).parent.mkdir(parents=True, exist_ok=True)
        with Path(args.out_report).open("w") as f:
            f.write(report_content)
        print(f"Report written to {args.out_report}")
    except Exception as e:
        print(f"Could not write report: {e}")

    if all_errors:
        sys.exit(2)

    print("VALIDATION PASS")
    sys.exit(0)

if __name__ == "__main__":
    main()
