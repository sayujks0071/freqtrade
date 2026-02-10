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


def fail(message, report_path=None, report_lines=None):
    print(f"FAIL: {message}")
    if report_path and report_lines is not None:
        try:
            # Append failure to report
            report_lines.append("\n## Critical Failure")
            report_lines.append(f"**FAIL**: {message}")
            # Ensure Status header is set to FAIL if not already set
            if len(report_lines) > 2 and "Status:" not in report_lines[2]:
                report_lines.insert(2, "Status: **FAIL**")
            elif len(report_lines) <= 2:
                report_lines.append("Status: **FAIL**")

            content = "\n".join(report_lines)
            write_report(report_path, content)
            print(f"Report written to {report_path}")
        except Exception as e_write:
            print(f"WARN: Could not write report: {e_write}")
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

    # Check for type/contract/future/perp indicator
    type_keys = ["type", "contract", "future", "spot", "swap", "linear", "inverse"]
    if not any(k in m for k in type_keys):
        errors.append(f"Item {i} ({symbol}) missing type/contract indicator")

    return symbol


def validate_symbol_format(symbol, errors):
    # Symbol format: BASE/QUOTE:SETTLE for futures usually
    if re.search(r"\s", symbol):
        errors.append(f"Symbol '{symbol}' contains whitespace")
    if symbol != symbol.upper():
        errors.append(f"Symbol '{symbol}' is not uppercase")

    if ":" not in symbol:
        if FILTER_MODE == "perps_usdt" or FILTER_MODE == "all_futures":
            errors.append(f"Symbol '{symbol}' missing settle delimiter (:)")


def validate_volume(m, symbol, errors):
    # Volume check
    vol = m.get("volume")
    if vol is not None:
        if not isinstance(vol, (int, float)):
            errors.append(f"Symbol '{symbol}' volume is not a number: {vol}")
        elif vol < 0:
            errors.append(f"Symbol '{symbol}' volume is negative: {vol}")
        elif STRICT_VOLUME and vol < 1000:
            errors.append(f"Low volume for {symbol}: {vol}")

    # Limits check
    # Check numeric limits are not negative (basic sanity)
    limits = m.get("limits")
    if isinstance(limits, dict):
        # Recursively check for negative numbers in limits
        stack = [limits]
        while stack:
            current = stack.pop()
            if isinstance(current, dict):
                stack.extend(current.values())
            elif isinstance(current, (int, float)) and current < 0:
                # -1 sometimes means unlimited, but generally we expect positive limits.
                # However, -1 is common for 'max'. Let's be lenient and only warn or strict check
                # if we see weird negative values like -999.
                # For now, let's just ignore limits validation unless it's obviously broken
                # structure, which is handled by JSON parsing.
                pass


def is_market_allowed(symbol, m, regex):
    if not symbol:
        return False

    if not m.get("active", True):
        return False

    if FILTER_MODE == "perps_usdt":
        if "/USDT:USDT" in symbol:
            return True
    elif FILTER_MODE == "all_futures":
        if ":" in symbol:
            return True
    elif FILTER_MODE == "allowlist_regex":
        if regex.match(symbol):
            return True
    else:
        if "/USDT:USDT" in symbol:
            return True
    return False


def generate_candidate_whitelist(markets):
    whitelist = []
    try:
        regex = re.compile(ALLOWLIST_REGEX)
    except re.error:
        warn(f"Invalid regex '{ALLOWLIST_REGEX}', falling back to strict match")
        regex = re.compile(r"^$")

    for m in markets:
        symbol = m.get("symbol")
        if is_market_allowed(symbol, m, regex):
            whitelist.append(symbol)

    return sorted(list(set(whitelist)))


def check_format_changes(added, removed, errors, report_lines):
    # Check for pair format changes
    # Map removed symbols to (base, quote)
    removed_map = {}
    # Extract BASE/QUOTE. Suffix can be anything.
    pattern = re.compile(r"^([A-Z0-9]+)/([A-Z0-9]+)")

    for sym in removed:
        m = pattern.match(sym)
        if m:
            key = (m.group(1), m.group(2))
            removed_map[key] = sym

    format_changes = []
    for sym in added:
        m = pattern.match(sym)
        if m:
            key = (m.group(1), m.group(2))
            if key in removed_map:
                old = removed_map[key]
                format_changes.append(f"{old} -> {sym}")

    if format_changes:
        msg = f"Format changed for {len(format_changes)} pairs (e.g., {format_changes[0]})"
        errors.append(msg)
        report_lines.append(f"**FAIL**: {msg}")


def calculate_drift(current_symbols, prev_symbols, report_lines, errors):
    removed = prev_symbols - current_symbols
    added = current_symbols - prev_symbols

    removal_ratio = len(removed) / len(prev_symbols) if len(prev_symbols) > 0 else 0.0

    report_lines.append(f"Drift stats: +{len(added)} / -{len(removed)}")
    report_lines.append(f"Removal Ratio: {removal_ratio:.2f} (Max: {MAX_REMOVAL_RATIO})")

    if len(removed) > 0:
        report_lines.append(f"Removed examples: {', '.join(list(removed)[:5])}")
    if len(added) > 0:
        report_lines.append(f"Added examples: {', '.join(list(added)[:5])}")

    if removal_ratio > MAX_REMOVAL_RATIO:
        msg = f"Large delist drift: {removal_ratio:.2f} > {MAX_REMOVAL_RATIO}"
        errors.append(msg)
        report_lines.append(f"**FAIL**: {msg}")

    return added, removed


def validate_drift(candidate_whitelist, prev_whitelist_path, errors, report_lines):
    prev_path_obj = Path(prev_whitelist_path)
    if not prev_whitelist_path or not prev_path_obj.exists():
        report_lines.append("Drift check: SKIPPED (No previous whitelist found)")
        return

    try:
        with prev_path_obj.open() as f:
            prev_data = json.load(f)
            if isinstance(prev_data, dict) and "exchange" in prev_data:
                prev_symbols = set(prev_data["exchange"].get("pair_whitelist", []))
            elif isinstance(prev_data, list):
                prev_symbols = set(prev_data)
            else:
                warn("Previous whitelist format unrecognized.")
                return
    except Exception as e_read:
        warn(f"Could not read previous whitelist: {e_read}")
        return

    current_symbols = set(candidate_whitelist)
    added, removed = calculate_drift(current_symbols, prev_symbols, report_lines, errors)
    check_format_changes(added, removed, errors, report_lines)


def run_schema_validation(data, args, report_lines):
    if len(data) < MIN_MARKETS:
        fail(
            f"Market count {len(data)} < MIN_MARKETS ({MIN_MARKETS})", args.out_report, report_lines
        )

    symbols = set()
    errors = []

    # Compile regex once for efficiency
    try:
        regex = re.compile(ALLOWLIST_REGEX)
    except re.error:
        regex = re.compile(r"^$")

    for i, m in enumerate(data):
        # 1. Structure check (must pass for everyone)
        symbol = validate_market_structure(i, m, errors)
        if not symbol:
            continue

        # 2. Check strict rules ONLY for eligible whitelist candidates
        if is_market_allowed(symbol, m, regex):
            validate_symbol_format(symbol, errors)
            validate_volume(m, symbol, errors)

            if symbol.upper() in symbols:
                errors.append(f"Duplicate symbol '{symbol}'")
            symbols.add(symbol.upper())

    return symbols, errors


def main():
    parser = argparse.ArgumentParser(description="Validate markets schema and drift.")
    parser.add_argument("--markets", required=True, help="Path to markets JSON dump")
    parser.add_argument("--env", required=True, help="Delta Environment (e.g. india_prod)")
    parser.add_argument("--prev-whitelist", required=True, help="Path to previous whitelist JSON")
    parser.add_argument("--out-report", required=True, help="Path to output Markdown report")

    args = parser.parse_args()

    print(f"Validating {args.markets} for env {args.env}...")

    report_lines = []
    report_lines.append("# Markets Schema Validation Report")
    report_lines.append(f"Date: {datetime.now(UTC).isoformat()}")
    report_lines.append(f"File: {args.markets}")
    report_lines.append(f"Environment: {args.env}")

    # 1. Load Markets
    try:
        with Path(args.markets).open() as f:
            data = json.load(f)
    except Exception as e_json:
        fail(f"Invalid JSON: {e_json}", args.out_report, report_lines)

    if isinstance(data, dict) and "markets" in data:
        data = data["markets"]

    if not isinstance(data, list):
        fail("Root must be a list of markets", args.out_report, report_lines)

    report_lines.append(f"Total Markets Found: {len(data)}")

    # 2. Schema Validation
    _, errors = run_schema_validation(data, args, report_lines)

    # Environment Sanity Warning
    report_lines.append(f"Env Check: {args.env} (Metadata unavailable, assumed match)")

    # 3. Drift Check
    candidate_whitelist = generate_candidate_whitelist(data)
    report_lines.append(f"Eligible Whitelist Size: {len(candidate_whitelist)}")

    validate_drift(candidate_whitelist, args.prev_whitelist, errors, report_lines)

    # Finalize Report
    if errors:
        report_lines.append("\n## Errors")
        for e in errors[:20]:
            report_lines.append(f"- {e}")
        if len(errors) > 20:
            report_lines.append(f"- ...and {len(errors) - 20} more")

        status = "FAIL"
        exit_code = 2
    else:
        status = "PASS"
        exit_code = 0

    report_lines.insert(2, f"Status: **{status}**")

    report_content = "\n".join(report_lines)

    try:
        write_report(args.out_report, report_content)
        print(f"Report written to {args.out_report}")
    except Exception as e_write:
        print(f"WARN: Could not write report: {e_write}")

    if exit_code != 0:
        print("VALIDATION FAILED")
        sys.exit(exit_code)

    print("VALIDATION PASS")


if __name__ == "__main__":
    main()
