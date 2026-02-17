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
    # The requirement says: "Must match futures style: BASE/QUOTE:SETTLE ... OR a consistent CCXT format"
    # Given we are dealing with Delta Exchange futures/perps mostly, we expect the colon.
    # However, if using regex mode, we might be allowing spot markets or other formats.
    # Only enforce colon if specifically in futures modes.
    if FILTER_MODE in ["perps_usdt", "all_futures"]:
        if ":" not in symbol:
            errors.append(f"Symbol '{symbol}' missing settle delimiter (:) required for {FILTER_MODE}")


def validate_volume_limits(m, symbol, errors):
    # Check for clearly invalid numeric fields
    # numeric fields to check: volume, precision, limits

    # Volume
    # Freqtrade dump usually puts quoteVolume in 'quoteVolume' or just 'volume' depending on exchange
    # We check standard ccxt fields if present
    for key in ["volume", "quoteVolume"]:
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

    # Optionally filter out near-zero volume markets if volume is available
    # Warn if volume is very low (e.g. < 1000 quote currency units)
    # This assumes 'quoteVolume' or 'volume' is in quote currency (usually USDT)
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
         except:
             pass


def validate_environment_sanity(data, env, errors):
    # Confirm the dump corresponds to the intended DELTA_ENV
    # We can check if any market has 'info' field with exchange specific data
    # Delta API usually returns 'symbol', 'contract_type', etc.
    # Or we can check if the exchange id matches.
    # Freqtrade dump has 'exchange_id' at top level sometimes? No, it's a list of markets usually.
    # But if we use --print-json, it might be just the list.

    # Check a few markets to see if they look like Delta markets
    # Delta symbols usually are like BTCUSDT (futures) or BTC-USDT (spot) in raw api,
    # but Freqtrade/CCXT converts them.
    # We can't easily check URL unless it's in the dump.

    # If we have 'info' dict in markets, we might see something.
    # Let's check for 'info' and see if it contains expected fields for Delta.
    # Delta 'info' usually has 'id', 'symbol', 'contract_type', 'status'.

    sample_market = next((m for m in data if "info" in m), None)
    if sample_market:
        info = sample_market["info"]
        # If it's Delta, it should have specific fields.
        if "product_specs" in info or "contract_type" in info or "quoting_asset" in info:
             pass # Looks like delta
        else:
             warn("Market 'info' does not look like Delta Exchange data. Is this the right exchange?")
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


def validate_drift(candidate_whitelist, prev_whitelist_path, errors):
    prev_path_obj = Path(prev_whitelist_path)
    if not prev_whitelist_path or not prev_path_obj.exists():
        print("No previous whitelist found. Skipping drift check.")
        return

    try:
        with prev_path_obj.open() as f:
            prev_data = json.load(f)

        # Handle if previous whitelist is freqtrade config format
        if isinstance(prev_data, dict) and "exchange" in prev_data and "pair_whitelist" in prev_data["exchange"]:
             prev_symbols = set(prev_data["exchange"]["pair_whitelist"])
        elif isinstance(prev_data, list):
             prev_symbols = set(prev_data)
        else:
             warn("Previous whitelist format unrecognized. Skipping drift check.")
             return

    except Exception as e:
        warn(f"Could not read previous whitelist: {e}")
        return

    current_symbols = set(candidate_whitelist)
    removed = prev_symbols - current_symbols
    added = current_symbols - prev_symbols

    removal_ratio = len(removed) / len(prev_symbols) if len(prev_symbols) > 0 else 0.0

    print(f"Drift stats: +{len(added)} / -{len(removed)} (Ratio: {removal_ratio:.2f})")

    # Check for large delist drift
    if removal_ratio > MAX_REMOVAL_RATIO:
        errors.append(
            f"Large delist drift — manual review required. "
            f"Removal ratio {removal_ratio:.2f} > MAX_REMOVAL_RATIO ({MAX_REMOVAL_RATIO})."
        )

    # Check for pair format changes
    # Identify pairs by Base/Quote (e.g. "BTC/USDT" from "BTC/USDT:USDT")
    # If we find the same Base/Quote with a different full symbol, flag it.

    def get_pair_key(s):
        # Extract base/quote part. Assuming format is BASE/QUOTE:SETTLE or BASE/QUOTE
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
        errors.append(f"Pair format changed for {len(format_changes)} pairs: {', '.join(format_changes[:5])}...")


def write_report(path, report_content):
    try:
        with Path(path).open("w") as f:
            f.write(report_content)
        print(f"Report written to {path}")
    except Exception as e:
        warn(f"Could not write report: {e}")


def main():
    parser = argparse.ArgumentParser(description="Validate Delta markets schema and whitelist drift.")
    parser.add_argument("--markets", required=True, help="Path to markets JSON file")
    parser.add_argument("--env", default="india_prod", help="Delta Environment (india_prod, global_prod)")
    parser.add_argument("--prev-whitelist", help="Path to previous whitelist JSON file")
    parser.add_argument("--out-report", default="user_data/reports/markets_schema_report.md", help="Path to output report")

    args = parser.parse_args()

    print(f"Validating {args.markets} for env {args.env}...")

    # Load markets
    try:
        with Path(args.markets).open() as f:
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

    errors = []

    # E) Environment Sanity
    validate_environment_sanity(data, args.env, errors)

    # Validation loop
    symbols = set()
    valid_markets = [] # For candidate whitelist generation, we only consider valid ones?
                       # Or we use all and let generate_whitelist filter?
                       # generate_whitelist filters by 'active' and symbol format.
                       # We should validate all markets in the dump.

    for i, m in enumerate(data):
        # C) Schema & D) Volume/Limits
        symbol = validate_market_structure(i, m, errors)
        if not symbol:
            continue

        # We only check format for symbols that are candidates for whitelist?
        # Requirement says: "For each market that will be eligible for whitelist"
        # So we should apply the filter first?
        # But we also want to validate the dump integrity generally.
        # Let's check format for all, but maybe be lenient on non-futures if we are in futures mode?
        # "Must match futures style ... OR a consistent CCXT format"
        # If the dump contains spot markets too, we shouldn't fail them if they are valid spot symbols (no settle).
        # But filter_markets usually selects futures.

        # Let's apply format check on *everything* that looks like it *should* be in our whitelist.
        # If FILTER_MODE is perps_usdt, we expect things ending in :USDT to be valid.

        # If we enforce "For each market that will be eligible for whitelist", we should use is_eligible logic.

        # Check uniqueness
        if symbol.lower() in symbols:
            errors.append(f"Duplicate symbol '{symbol}' (case-insensitive)")
        symbols.add(symbol.lower())

        # If eligible (based on current filter mode), check format strictly
        # We'll use a helper to check eligibility based on simple heuristic or reuse logic
        is_eligible = False
        if FILTER_MODE == "perps_usdt" and symbol.endswith("/USDT:USDT"):
             is_eligible = True
        elif FILTER_MODE == "all_futures": # Assume all in dump are futures if using this mode?
             is_eligible = True
        elif FILTER_MODE == "allowlist_regex":
             if re.match(ALLOWLIST_REGEX, symbol):
                 is_eligible = True
        else:
            # Default fallback in loop if filter mode is unknown or default
             if symbol.endswith("/USDT:USDT"):
                 is_eligible = True

        if is_eligible:
            validate_symbol_format(symbol, errors)
            validate_volume_limits(m, symbol, errors)
            valid_markets.append(m)

    # F) Drift Safety Gate
    candidate_whitelist = get_candidate_whitelist(data)

    # Check if candidate whitelist is empty
    if not candidate_whitelist:
         errors.append(f"Candidate whitelist is empty! Check FILTER_MODE ({FILTER_MODE}) and markets dump.")

    if args.prev_whitelist:
        validate_drift(candidate_whitelist, args.prev_whitelist, errors)

    # Report generation
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

    write_report(args.out_report, report_content)

    if errors:
        print("VALIDATION FAILED")
        sys.exit(2)
    else:
        print("VALIDATION PASS")
        sys.exit(0)


if __name__ == "__main__":
    main()
