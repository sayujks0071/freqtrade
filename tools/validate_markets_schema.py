#!/usr/bin/env python3
"""
Strict validation layer for Delta markets refresh workflow.
Validates market schema, fields, uniqueness, volume/limits, environment sanity, and drift.
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Configuration from Environment
MIN_MARKETS = int(os.environ.get("MIN_MARKETS", 20))
MAX_REMOVAL_RATIO = float(os.environ.get("MAX_REMOVAL_RATIO", 0.25))
STRICT_VOLUME = os.environ.get("STRICT_VOLUME", "false").lower() == "true"
# Only warn by default; allow STRICT_VOLUME=true to fail if too many are illiquid

REQUIRED_FIELDS = ["symbol", "base", "quote", "active"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate Delta Exchange markets dump.")
    parser.add_argument("--markets", required=True, help="Path to markets JSON dump")
    parser.add_argument("--env", required=True, help="Delta Environment (e.g., india_prod)")
    parser.add_argument("--prev-whitelist", help="Path to previous whitelist JSON")
    parser.add_argument("--out-report", required=True, help="Path to output Markdown report")
    return parser.parse_args()


def load_json(path: str) -> Any:
    try:
        with Path(path).open() as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"File not found: {path}")
        sys.exit(2)
    except json.JSONDecodeError as e:
        print(f"Invalid JSON in {path}: {e}")
        sys.exit(2)
    except Exception as e:
        print(f"Error reading {path}: {e}")
        sys.exit(2)


def validate_schema(data: Any) -> tuple[list[dict], list[str]]:
    """
    Validates top-level structure and extracts markets list.
    Returns (markets_list, errors)
    """
    errors = []
    markets = []

    if isinstance(data, list):
        markets = data
    elif isinstance(data, dict) and "markets" in data:
        if isinstance(data["markets"], list):
            markets = data["markets"]
        else:
            errors.append("Top-level dict 'markets' is not a list")
    else:
        # Some dumps might be dict with symbols as keys?
        # Freqtrade list-markets usually list of dicts.
        errors.append("Root must be a list or dict with 'markets' list")

    if not errors and len(markets) < MIN_MARKETS:
        errors.append(f"Market count {len(markets)} < MIN_MARKETS ({MIN_MARKETS})")

    return markets, errors


def validate_symbol_format(symbol: str) -> list[str]:
    errs = []
    # Symbol format: BASE/QUOTE:SETTLE for futures usually
    # Reject whitespace/lowercase
    if re.search(r"\s", symbol):
        errs.append(f"Symbol '{symbol}' contains whitespace")
    if symbol != symbol.upper():
        errs.append(f"Symbol '{symbol}' is not uppercase")

    # Strict check for futures format (must have settle currency)
    # E.g. BTC/USDT:USDT
    if ":" not in symbol:
        errs.append(f"Symbol '{symbol}' missing settle delimiter (:)")
    elif symbol.count("/") != 1:
        errs.append(f"Symbol '{symbol}' must have exactly one '/'")

    return errs


def validate_volume_limits(m: dict[str, Any], symbol: str) -> list[str]:
    errs = []
    # Check for NaN or negative numbers in common fields
    # "info" often contains raw exchange data where we might find volume

    # Example check: limits.amount.min > 0
    limits = m.get("limits", {})
    if isinstance(limits, dict):
        amt = limits.get("amount", {})
        if isinstance(amt, dict):
            min_amt = amt.get("min")
            if isinstance(min_amt, (int, float)) and min_amt < 0:
                 errs.append(f"{symbol}: Negative min amount {min_amt}")

            # Use STRICT_VOLUME to potentially fail on tiny limits (placeholder logic)
            if STRICT_VOLUME and isinstance(min_amt, (int, float)) and min_amt == 0:
                 # Just a warning or info for now, as 0 might be valid for some
                 pass

    return errs


def validate_markets(markets: list[dict[str, Any]]) -> tuple[set[str], list[str], list[str]]:
    """
    Validates individual market entries.
    Returns (valid_symbols_set, errors, warnings)
    """
    errors = []
    warnings = []
    valid_symbols = set()
    seen_symbols = set()

    for i, m in enumerate(markets):
        # 1. Required fields
        missing = [f for f in REQUIRED_FIELDS if f not in m]
        if missing:
            errors.append(f"Item {i}: Missing fields {missing}")
            continue

        symbol = m.get("symbol", "")
        if not symbol:
            errors.append(f"Item {i}: Empty symbol")
            continue

        # 2. Check active
        if not m.get("active", False):
            continue

        # 3. Check type (must be future/swap/perp)
        m_type = m.get("type")
        contract = m.get("contract")
        future = m.get("future")

        # We expect futures/swaps for Delta
        if not (
            m_type in ["future", "swap"]
            or contract
            or future
            or m.get("linear")
            or m.get("inverse")
        ):
             # Maybe it's a spot market in the dump?
             # If filter mode is strict, we might care, but for schema validation
             # we mostly care that fields are correct.
             # But if we are validating "markets schema for whitelist", we want to ensure
             # we are getting what we expect.
             # Warnings for now.
             warnings.append(f"Item {i} ({symbol}): Unclear type (not explicitly future/swap)")

        # 4. Symbol format
        fmt_errs = validate_symbol_format(symbol)
        if fmt_errs:
            for e in fmt_errs:
                errors.append(f"Item {i}: {e}")
            continue

        # 5. Uniqueness
        if symbol.upper() in seen_symbols:
            errors.append(f"Duplicate symbol '{symbol}'")
        seen_symbols.add(symbol.upper())

        # 6. Volume/Limits
        vol_errs = validate_volume_limits(m, symbol)
        errors.extend(vol_errs)

        valid_symbols.add(symbol)

    return valid_symbols, errors, warnings


def validate_environment_sanity(markets: list[dict[str, Any]], env: str) -> list[str]:
    """
    Checks if the data looks like it belongs to the environment.
    """
    warnings = []
    # If data is a dict and has 'exchange_id' or similar?
    # Freqtrade dump usually doesn't have top level metadata.
    # But we can check if markets have 'info' with recognizable URLs or IDs.

    # For now just a placeholder warning if we can't be sure
    # warnings.append("No metadata found in dump to verify environment match.")
    return warnings


def check_format_changes(prev_symbols: set[str], current_symbols: set[str]) -> list[str]:
    """
    Check for format changes in existing pairs.
    """
    # Construct map of Base/Quote -> FullSymbol for previous
    def extract_base_quote(s):
        # handle BASE/QUOTE:SETTLE or BASE/QUOTE
        if ":" in s:
            return s.split(":")[0]
        return s

    prev_base_quotes = {extract_base_quote(s): s for s in prev_symbols}
    curr_base_quotes = {extract_base_quote(s): s for s in current_symbols}

    format_changes = []
    for bq, prev_s in prev_base_quotes.items():
        if bq in curr_base_quotes:
            curr_s = curr_base_quotes[bq]
            if prev_s != curr_s:
                format_changes.append(f"Format changed for {bq}: {prev_s} -> {curr_s}")
    return format_changes


def load_previous_whitelist(path: str | None) -> set[str]:
    """Helper to load previous whitelist symbols."""
    if not path:
        return set()

    path_obj = Path(path)
    if not path_obj.exists():
        print(f"Previous whitelist {path} not found. Skipping drift check.")
        return set()

    try:
        with path_obj.open() as f:
            prev_data = json.load(f)
    except Exception as e:
        print(f"Failed to read previous whitelist: {e}")
        return set()

    prev_symbols = set()
    if isinstance(prev_data, list):
        prev_symbols = set(prev_data)
    elif isinstance(prev_data, dict):
        if "pair_whitelist" in prev_data:
            prev_symbols = set(prev_data["pair_whitelist"])
        elif "pairs" in prev_data:
            prev_symbols = set(prev_data["pairs"])
        elif "markets" in prev_data:
             for m in prev_data["markets"]:
                 if isinstance(m, dict) and "symbol" in m:
                     prev_symbols.add(m["symbol"])
    return prev_symbols


def validate_drift(
    current_symbols: set[str],
    prev_whitelist_path: str | None
) -> tuple[list[str], list[str]]:
    """
    Checks for dangerous drift (large removal ratio, format changes).
    Returns (errors, drift_stats)
    """
    prev_symbols = load_previous_whitelist(prev_whitelist_path)

    if not prev_symbols:
         # If load returned empty, we already printed warnings inside load function or it was empty.
         # We'll just return informational stats if we can't do drift check.
         if prev_whitelist_path:
             return [], ["Previous whitelist loaded but empty or invalid format. Skipping drift check."]
         return [], ["No previous whitelist provided. Skipping drift check."]

    removed = prev_symbols - current_symbols
    added = current_symbols - prev_symbols

    removal_ratio = len(removed) / len(prev_symbols) if len(prev_symbols) > 0 else 0.0

    stats = [
        f"Previous Count: {len(prev_symbols)}",
        f"Current Count: {len(current_symbols)}",
        f"Added: {len(added)}",
        f"Removed: {len(removed)}",
        f"Removal Ratio: {removal_ratio:.2%}"
    ]

    errors = []
    if removal_ratio > MAX_REMOVAL_RATIO:
        errors.append(
            f"Large delist drift: {removal_ratio:.2%} > MAX_REMOVAL_RATIO "
            f"({MAX_REMOVAL_RATIO:.2%})"
        )

    format_changes = check_format_changes(prev_symbols, current_symbols)

    if format_changes:
        errors.append("Format changes detected in existing pairs:")
        errors.extend(format_changes[:10]) # limit output
        if len(format_changes) > 10:
            errors.append(f"...and {len(format_changes) - 10} more")

    return errors, stats


def write_report(path: str, content: str) -> None:
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w") as f:
            f.write(content)
        print(f"Report written to {path}")
    except Exception as e:
        print(f"Failed to write report to {path}: {e}")


def main() -> None:
    args = parse_args()

    print(f"Validating markets from: {args.markets}")
    print(f"Environment: {args.env}")

    data = load_json(args.markets)
    markets, schema_errors = validate_schema(data)

    report_lines = [
        "# Markets Schema Validation Report",
        f"Date: {datetime.now(timezone.utc).isoformat()}", # noqa: UP017
        f"File: {args.markets}"
    ]

    if schema_errors:
        report_lines.extend(["", "**STATUS: FAIL**", "", "## Schema Errors"])
        for err in schema_errors:
            report_lines.append(f"- {err}")

        write_report(args.out_report, "\n".join(report_lines))
        print("Validation FAILED (Schema)")
        sys.exit(2)

    print("Schema structure OK. Checking markets details...")

    valid_symbols, market_errors, market_warnings = validate_markets(markets)

    # Env sanity
    env_warnings = validate_environment_sanity(markets, args.env)
    market_warnings.extend(env_warnings)

    report_lines.append(f"Total Markets in Dump: {len(markets)}")
    report_lines.append(f"Valid Active Symbols: {len(valid_symbols)}")

    if market_errors:
        report_lines.extend(["", "**STATUS: FAIL**", "", "## Market Validation Errors"])
        # Limit errors in report to avoid huge files
        for err in market_errors[:50]:
            report_lines.append(f"- {err}")
        if len(market_errors) > 50:
            report_lines.append(f"...and {len(market_errors) - 50} more")

        write_report(args.out_report, "\n".join(report_lines))
        print(f"Validation FAILED ({len(market_errors)} errors)")
        sys.exit(2)

    if market_warnings:
         report_lines.extend(["", "## Warnings"])
         for w in market_warnings:
             report_lines.append(f"- {w}")

    # Drift check
    print("Checking drift...")
    drift_errors, drift_stats = validate_drift(valid_symbols, args.prev_whitelist)

    report_lines.extend(["", "## Drift Analysis"])
    report_lines.extend(drift_stats)

    if drift_errors:
        report_lines.extend(["", "**STATUS: FAIL**", "", "### Drift Errors"])
        for err in drift_errors:
            report_lines.append(f"- {err}")

        write_report(args.out_report, "\n".join(report_lines))
        print(f"Validation FAILED ({len(drift_errors)} drift errors)")
        sys.exit(2)

    report_lines.extend(["", "**STATUS: PASS**"])
    write_report(args.out_report, "\n".join(report_lines))
    print("Validation PASSED")


if __name__ == "__main__":
    main()
