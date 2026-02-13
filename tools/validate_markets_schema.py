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
# Some dumps might use 'type', others 'contract', etc.
REQUIRED_ONE_OF = ["type", "contract", "future", "perp", "linear", "spot"]


def fail(message):
    print(f"FAIL: {message}")
    sys.exit(2)


def warn(message):
    print(f"WARN: {message}")


def is_eligible(market):
    symbol = market.get("symbol", "")
    # If explicitly inactive, usually we skip validation unless we want to validate inactive markets too.
    # But for whitelist generation, we only care about active ones.
    # The requirement says "For each market that will be eligible for whitelist".
    if not market.get("active", True):
        return False

    regex = re.compile(ALLOWLIST_REGEX)

    if FILTER_MODE == "perps_usdt":
        return "/USDT:USDT" in symbol
    elif FILTER_MODE == "all_futures":
        # We assume the dump contains futures if that's what we asked for.
        # But we can check 'type' if available.
        # For now, just accept all active symbols if mode is all_futures
        return True
    elif FILTER_MODE == "allowlist_regex":
        return bool(regex.match(symbol))
    else:
        # Default
        return "/USDT:USDT" in symbol


def validate_market_structure(i, m, errors):
    # Required fields
    for f in REQUIRED_FIELDS:
        if f not in m:
            errors.append(f"Item {i} missing field '{f}'")

    # Check at least one type indicator
    has_type = False
    for f in REQUIRED_ONE_OF:
        if f in m:
            has_type = True
            break
    # Also check if 'info' has type info? usually top level fields are normalized by ccxt
    if not has_type:
         errors.append(f"Item {i} missing any type indicator ({', '.join(REQUIRED_ONE_OF)})")

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

    # Strict check for futures format (must have settle currency)
    # The requirement says: "Must match futures style: BASE/QUOTE:SETTLE ... OR a consistent CCXT format discovered from dump."
    # If FILTER_MODE implies futures, we expect colon.
    if "perps" in FILTER_MODE or "futures" in FILTER_MODE:
        if ":" not in symbol:
             errors.append(f"Symbol '{symbol}' missing settle delimiter (:)")


def validate_volume(m, symbol, errors):
    # Volume check (if strict)
    # Freqtrade dump usually standardizes some fields.
    # We look for 'info' -> 'volume_24h' or top level 'volume'
    vol = None
    if "volume" in m:
        vol = m.get("volume")
    elif "info" in m and isinstance(m["info"], dict):
        # Try to find volume in raw info (exchange specific)
        # Delta exchange might have 'volume' or 'turnover'
        pass

    if vol is not None:
         try:
             vol_float = float(vol)
             if vol_float < 0:
                 errors.append(f"Negative volume for {symbol}: {vol}")
             if STRICT_VOLUME and vol_float < 1000:
                 errors.append(f"Low volume for {symbol}: {vol}")
         except (ValueError, TypeError):
             errors.append(f"Invalid volume for {symbol}: {vol}")


def validate_env_sanity(data, env_name, errors):
    # Check for recognizable base URL / exchange id
    # We check the first market's info
    if not data:
        return

    m = data[0]
    info = m.get("info", {})
    if not isinstance(info, dict):
        return

    # Check if we can find any env indicator
    # For Delta, maybe 'symbol' or 'contract_type' doesn't help much with env.
    # But if we have url in info? Unlikely in list-markets dump.
    # We might have to skip if no clear indicator.
    # Requirement: "checking for a recognizable base URL / exchange id if available in metadata; otherwise log a warning."

    # If we assume 'exchange_id' is present (it's not standard in market list, usually in exchange describe)
    # We can warn if we are completely unsure.
    # But warnings shouldn't fail the build.

    # Let's verify if the list seems to match what we expect.
    # If env is 'india', maybe some symbols are specific?
    # Without specific knowledge of Delta India vs Global symbol differences, this is hard.
    # I will log a warning that sanity check is limited.
    warn(f"Environment sanity check limited (env={env_name}). Verify manually if needed.")


def validate_drift(candidate_path, prev_path, errors):
    if not prev_path or not Path(prev_path).exists():
        print("No previous whitelist found. Skipping drift check.")
        return [], 0.0, 0, 0

    cand_symbols = set()
    prev_symbols = set()

    try:
        with Path(candidate_path).open() as f:
            cand_data = json.load(f)
            cand_symbols = set(cand_data.get("exchange", {}).get("pair_whitelist", []))

        with Path(prev_path).open() as f:
            prev_data = json.load(f)
            prev_symbols = set(prev_data.get("exchange", {}).get("pair_whitelist", []))

    except Exception as e:
        warn(f"Could not read whitelists for drift check: {e}")
        return [], 0.0, 0, 0

    removed = prev_symbols - cand_symbols
    added = cand_symbols - prev_symbols

    removal_ratio = len(removed) / len(prev_symbols) if len(prev_symbols) > 0 else 0.0

    if removal_ratio > MAX_REMOVAL_RATIO:
        errors.append(
            f"Removal ratio {removal_ratio:.2f} > MAX_REMOVAL_RATIO "
            f"({MAX_REMOVAL_RATIO}). Large delist drift — manual review required"
        )

    return list(removed), removal_ratio, len(added), len(prev_symbols)


def write_report(path, status, count, eligible_count, whitelist_count, errors, drift_stats):
    removed, ratio, added_count, prev_count = drift_stats

    report = f"""# Markets Schema Validation Report
Date: {datetime.now(UTC).isoformat()}
Status: {status}

## Counts
- Total Markets: {count}
- Eligible Markets: {eligible_count}
- Whitelist Size: {whitelist_count}
- Previous Whitelist Size: {prev_count}

## Drift Analysis
- Added: {added_count}
- Removed: {len(removed)}
- Removal Ratio: {ratio:.2f} (Max: {MAX_REMOVAL_RATIO})
"""
    if removed:
        report += "\n### Removed Pairs (Sample)\n"
        for p in removed[:10]:
            report += f"- {p}\n"
        if len(removed) > 10:
            report += f"... and {len(removed) - 10} more\n"

    if errors:
        report += "\n## Errors\n"
        for e in errors[:20]:
            report += f"- {e}\n"
        if len(errors) > 20:
             report += f"... and {len(errors) - 20} more\n"

    try:
        # Ensure directory exists
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with Path(path).open("w") as f:
            f.write(report)
        print(f"Report written to {path}")
    except Exception as e:
        warn(f"Could not write report: {e}")


def main():
    parser = argparse.ArgumentParser(description="Validate Markets Schema")
    parser.add_argument("--markets", required=True, help="Path to markets JSON")
    parser.add_argument("--candidate-whitelist", required=True, help="Path to candidate whitelist JSON")
    parser.add_argument("--prev-whitelist", help="Path to previous whitelist JSON")
    parser.add_argument("--env", help="Environment name", default="unknown")
    parser.add_argument("--out-report", required=True, help="Path to output markdown report")

    args = parser.parse_args()

    print(f"Validating {args.markets} for env {args.env}...")

    # Load Markets
    try:
        with Path(args.markets).open() as f:
            data = json.load(f)
    except Exception as e:
        fail(f"Invalid JSON in markets file: {e}")

    # Handle list-markets output structure
    if isinstance(data, dict) and "markets" in data:
        data = data["markets"]

    if not isinstance(data, list):
        fail("Root must be a list of markets or dict with 'markets' key")

    if len(data) < MIN_MARKETS:
        fail(f"Market count {len(data)} < MIN_MARKETS ({MIN_MARKETS})")

    # Validate Schema
    symbols = set()
    errors = []
    eligible_count = 0

    validate_env_sanity(data, args.env, errors)

    for i, m in enumerate(data):
        # First check eligibility
        # But we should validate structure even if not eligible?
        # Requirement: "C) For each market that will be eligible for whitelist:"
        # So we only strictly validate eligible markets.
        # However, if required fields are missing, we might not be able to determine eligibility safely.
        # But 'symbol' is required for eligibility check.

        # Let's do basic structure check first, then eligibility, then format check.

        # Check if 'symbol' exists first
        if "symbol" not in m:
             # If symbol is missing, we can't do much. Report error?
             # But if it's a completely broken entry, yes.
             errors.append(f"Item {i} missing symbol")
             continue

        if not is_eligible(m):
            continue

        eligible_count += 1

        symbol = validate_market_structure(i, m, errors)
        if not symbol:
            continue

        validate_symbol_format(symbol, errors)

        # Uniqueness
        if symbol.lower() in symbols:
            errors.append(f"Duplicate symbol '{symbol}' (case-insensitive)")
        symbols.add(symbol.lower())

        validate_volume(m, symbol, errors)

    # Load Candidate Whitelist to get count
    whitelist_count = 0
    try:
        with Path(args.candidate_whitelist).open() as f:
            c_data = json.load(f)
            whitelist_count = len(c_data.get("exchange", {}).get("pair_whitelist", []))
    except Exception as e:
        errors.append(f"Could not read candidate whitelist: {e}")

    # Validate Drift
    drift_stats = ([], 0.0, 0, 0)
    drift_stats = validate_drift(args.candidate_whitelist, args.prev_whitelist, errors)

    status = "FAIL" if errors else "PASS"

    write_report(args.out_report, status, len(data), eligible_count, whitelist_count, errors, drift_stats)

    if errors:
        print(f"FAIL: Validation failed with {len(errors)} errors.")
        sys.exit(2)

    print("VALIDATION PASS")


if __name__ == "__main__":
    main()
