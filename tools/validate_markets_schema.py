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

REQUIRED_FIELDS = ["symbol", "base", "quote", "active"]
TYPE_FIELDS = ["type", "contract", "future", "perp"]


def fail(message, report_lines):
    full_msg = f"FAIL: {message}"
    print(full_msg)
    report_lines.append("**STATUS: FAIL**")
    report_lines.append(f"Reason: {message}")
    return 2


def warn(message, report_lines):
    full_msg = f"WARN: {message}"
    print(full_msg)
    report_lines.append(f"- WARN: {message}")


def validate_market_structure(i, m, errors):
    # Required fields
    missing = [f for f in REQUIRED_FIELDS if f not in m]
    if missing:
        errors.append(f"Item {i} missing fields: {missing}")

    # Type check (one of type/contract/future/perp)
    if not any(f in m for f in TYPE_FIELDS):
        errors.append(f"Item {i} missing type indicator (one of {TYPE_FIELDS})")

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

    # Strict check for futures format (must have settle currency if it's a future)
    # The prompt says: "Must match futures style: BASE/QUOTE:SETTLE ... OR a consistent CCXT format"
    # We enforce presence of ':' for Delta futures as per prompt example.
    if ":" not in symbol:
        errors.append(f"Symbol '{symbol}' missing settle delimiter (:)")


def validate_numeric(m, symbol, errors):
    # Numeric sanity checks
    # Check volume if present
    if "volume" in m:
        vol = m.get("volume")
        if vol is not None:
            if not isinstance(vol, (int, float)):
                errors.append(f"Volume for {symbol} is not numeric: {vol}")
            elif vol < 0:
                errors.append(f"Volume for {symbol} is negative: {vol}")
            elif STRICT_VOLUME and vol < 1000:
                errors.append(f"Low volume for {symbol}: {vol}")

    # Check limits if present (e.g., cost min/max)
    if "limits" in m and isinstance(m["limits"], dict):
        limits = m["limits"]
        for k, v in limits.items():
            if isinstance(v, dict):
                for sk, sv in v.items():
                    if isinstance(sv, (int, float)) and sv < 0:
                        errors.append(f"Limit {k}.{sk} for {symbol} is negative: {sv}")


def validate_schema(data, report_lines):
    if not isinstance(data, list):
        return fail("Root must be a list of markets", report_lines)

    if len(data) < MIN_MARKETS:
        return fail(f"Market count {len(data)} < MIN_MARKETS ({MIN_MARKETS})", report_lines)

    symbols = set()
    errors = []

    # Check for duplicates
    seen_symbols = set()

    for i, m in enumerate(data):
        symbol = validate_market_structure(i, m, errors)
        if not symbol:
            continue

        validate_symbol_format(symbol, errors)

        # Uniqueness (case-insensitive check handled by validate_symbol_format
        # forcing uppercase check)
        if symbol in seen_symbols:
            errors.append(f"Duplicate symbol '{symbol}'")
        seen_symbols.add(symbol)
        symbols.add(symbol)

        validate_numeric(m, symbol, errors)

    if errors:
        report_lines.append("## Schema Errors")
        for e in errors[:20]:
            report_lines.append(f"- {e}")
        if len(errors) > 20:
            report_lines.append(f"- ...and {len(errors) - 20} more")
        return fail(f"Found {len(errors)} schema errors", report_lines)

    report_lines.append(f"- Total Markets: {len(data)}")
    report_lines.append(f"- Valid Symbols: {len(symbols)}")
    return symbols


def validate_env(data_meta, env, report_lines):
    # data_meta might be the exchange dict if available, or None
    # If the input was just a list, we might not have metadata.
    if not data_meta:
        warn("No exchange metadata found to verify environment.", report_lines)
        return

    # Check if 'id' or 'urls' match expected env
    # This is heuristic.
    # Delta Env: india_prod, global_prod, india_testnet

    exchange_id = data_meta.get("id", "").lower()
    urls = data_meta.get("urls", {})
    api_url = urls.get("api", "")
    if isinstance(api_url, dict):
        api_url = api_url.get("public", "")

    report_lines.append("## Environment Check")
    report_lines.append(f"- Expected: {env}")
    report_lines.append(f"- Found ID: {exchange_id}")
    report_lines.append(f"- Found API: {api_url}")

    # Simple checks
    if "testnet" in env and "testnet" not in api_url and "testnet" not in exchange_id:
        warn(
            f"Environment mismatch? Expected {env} but URL/ID doesn't look like testnet.",
            report_lines,
        )
    elif "india" in env and "india" not in api_url and "india" not in exchange_id:
        # This might be valid if they share global URL but different endpoints
        # but usually india has specific URL
        warn(
            f"Environment mismatch? Expected {env} but URL/ID doesn't look like India.",
            report_lines,
        )


def load_whitelist(path):
    if not path or not Path(path).exists():
        return set()
    try:
        with Path(path).open() as f:
            data = json.load(f)
            # Handle freqtrade whitelist format: {"exchange": {"pair_whitelist": [...]}}
            if isinstance(data, dict) and "exchange" in data:
                return set(data["exchange"].get("pair_whitelist", []))
            elif isinstance(data, list):
                return set(data)
            else:
                return set()
    except Exception as e:
        print(f"Error reading whitelist {path}: {e}")
        return set()


def validate_drift(candidate_path, prev_path, report_lines):
    candidate_symbols = load_whitelist(candidate_path)
    prev_symbols = load_whitelist(prev_path)

    if not prev_symbols:
        report_lines.append("## Drift Check")
        report_lines.append("- No previous whitelist found. Skipping drift check.")
        return 0

    removed = prev_symbols - candidate_symbols
    added = candidate_symbols - prev_symbols

    # Calculate ratio based on previous size
    removal_ratio = len(removed) / len(prev_symbols) if len(prev_symbols) > 0 else 0.0

    report_lines.append("## Drift Check")
    report_lines.append(f"- Previous Whitelist Size: {len(prev_symbols)}")
    report_lines.append(f"- Candidate Whitelist Size: {len(candidate_symbols)}")
    report_lines.append(f"- Added: {len(added)}")
    report_lines.append(f"- Removed: {len(removed)}")
    report_lines.append(f"- Removal Ratio: {removal_ratio:.2f}")

    if removal_ratio > MAX_REMOVAL_RATIO:
        return fail(
            f"Large delist drift: {removal_ratio:.2f} > MAX ({MAX_REMOVAL_RATIO}). "
            "Manual review required.",
            report_lines,
        )

    # Check format change (strict check for new symbols)
    # The prompt says: "If pair-format changed for any existing pair, FAIL"
    # Since we can't track pair identity easily, we check if *any* symbol in candidate whitelist
    # fails the strict format check, or if the *dominant* format changed (heuristic).
    # But we already validated format for ALL markets in validate_schema.
    # So here we just check if any symbol in candidate whitelist is weird.

    for s in candidate_symbols:
        # Re-verify format for whitelist specifically
        if ":" not in s:
            return fail(f"Candidate whitelist contains invalid symbol format: {s}", report_lines)

    return 0


def write_report(path, lines):
    try:
        with Path(path).open("w") as f:
            f.write("\n".join(lines))
        print(f"Report written to {path}")
    except Exception as e:
        print(f"Could not write report: {e}")


def main():
    parser = argparse.ArgumentParser(description="Validate markets schema and check for drift.")
    parser.add_argument("--markets", required=True, help="Path to markets JSON dump")
    parser.add_argument(
        "--candidate-whitelist", required=False, help="Path to candidate whitelist JSON"
    )
    parser.add_argument("--prev-whitelist", required=False, help="Path to previous whitelist JSON")
    parser.add_argument(
        "--env",
        required=False,
        default="india_prod",
        help="Target environment (e.g., india_prod)",
    )
    parser.add_argument("--out-report", required=True, help="Path to output Markdown report")

    args = parser.parse_args()

    report_lines = [
        "# Markets Schema Validation Report",
        f"Date: {datetime.now(UTC).isoformat()}",
        f"Env: {args.env}",
        f"File: {args.markets}",
        "",
    ]

    try:
        with Path(args.markets).open() as f:
            data = json.load(f)
    except Exception as e:
        report_lines.append("**FATAL: Invalid JSON in markets file**")
        report_lines.append(str(e))
        write_report(args.out_report, report_lines)
        sys.exit(2)

    # Extract list and metadata
    markets_list = []
    metadata = {}
    if isinstance(data, list):
        markets_list = data
    elif isinstance(data, dict):
        markets_list = data.get("markets", [])
        metadata = data  # Assume top level dict is metadata if 'markets' key exists
    else:
        fail("Invalid JSON structure (neither list nor dict)", report_lines)
        write_report(args.out_report, report_lines)
        sys.exit(2)

    # Validate Schema
    res = validate_schema(markets_list, report_lines)
    if isinstance(res, int) and res != 0:
        # Failed
        write_report(args.out_report, report_lines)
        sys.exit(res)

    # Validate Environment
    validate_env(metadata, args.env, report_lines)

    # Validate Drift
    if args.candidate_whitelist:
        res = validate_drift(args.candidate_whitelist, args.prev_whitelist, report_lines)
        if res != 0:
            write_report(args.out_report, report_lines)
            sys.exit(res)

    report_lines.append("")
    report_lines.append("**STATUS: PASS**")
    write_report(args.out_report, report_lines)
    sys.exit(0)


if __name__ == "__main__":
    main()
