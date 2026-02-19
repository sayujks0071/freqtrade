#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
from datetime import timezone, datetime
from pathlib import Path

# Configuration defaults
DEFAULT_MIN_MARKETS = 20
DEFAULT_MAX_REMOVAL_RATIO = 0.25
DEFAULT_STRICT_VOLUME = False

REQUIRED_FIELDS = ["symbol", "base", "quote", "active"]


def fail(message, report_path=None, report_content=None):
    print(f"FAIL: {message}")
    if report_path and report_content:
        try:
            with open(report_path, "w") as f:
                f.write(report_content)
            print(f"Report written to {report_path}")
        except Exception as e:
            print(f"WARN: Could not write report: {e}")
    sys.exit(2)


def warn(message):
    print(f"WARN: {message}")


def validate_market_structure(i, m, errors):
    # Required fields
    for f in REQUIRED_FIELDS:
        if f not in m:
            errors.append(f"Item {i} missing field '{f}'")
            return None

    symbol = m.get("symbol", "")
    if not symbol:
        errors.append(f"Item {i} has empty symbol")
        return None

    # Check type/contract/future/perp indicator (at least one)
    # Common fields: type, contract, future, spot, swap, linear, inverse
    type_indicators = ["type", "contract", "future", "spot", "swap", "linear", "inverse", "prediction"]
    has_type = any(k in m for k in type_indicators)
    if not has_type:
        # Freqtrade dump often normalizes this but let's check
        # Sometimes 'info' has raw data.
        # But wait, ccxt structure usually has 'type': 'future', 'swap', etc.
        # Let's just check if 'type' exists or 'contract' is true/false if present
        if "type" not in m and "contract" not in m:
             errors.append(f"Item {i} ({symbol}) missing type/contract indicator")

    return symbol


def validate_symbol_format(symbol, errors, strict_futures=True):
    # Symbol format: BASE/QUOTE:SETTLE for futures usually
    # Reject whitespace/lowercase
    if re.search(r"\s", symbol):
        errors.append(f"Symbol '{symbol}' contains whitespace")
    if symbol != symbol.upper():
        errors.append(f"Symbol '{symbol}' is not uppercase")

    # Strict check for futures format (must have settle currency)
    # The requirement says: "Must match futures style: BASE/QUOTE:SETTLE ... OR a consistent CCXT format discovered from dump."
    # If strict_futures is True, we enforce it.
    if strict_futures and ":" not in symbol:
        errors.append(f"Symbol '{symbol}' missing settle delimiter (:)")


def validate_numeric(m, symbol, errors, strict_volume):
    # Reject markets with clearly invalid numeric fields (NaN, negative, absurdly huge)
    # Common numeric fields: limits (amount, price, cost), info (raw data)

    # Check limits if available
    if "limits" in m and isinstance(m["limits"], dict):
        for k, v in m["limits"].items():
             if isinstance(v, dict):
                 for subk, subv in v.items():
                     if isinstance(subv, (int, float)):
                         if subv < 0:
                             errors.append(f"Symbol '{symbol}' has negative limit {k}.{subk}: {subv}")

    # Volume check
    # CCXT/Freqtrade usually puts volume in 'info' or top level if 24h ticker
    # But list-markets often just lists metadata, not ticker data.
    # If volume is present, check it.
    # If strict_volume is True, fail if volume < 1000 (if present)

    # Note: list-markets often doesn't have volume unless it fetched tickers too.
    # But if it does:
    vol = None
    if "quoteVolume" in m:
         vol = m["quoteVolume"]
    elif "info" in m and "volume_24h" in m["info"]: # specific to some exchanges
         vol = m["info"]["volume_24h"]

    if vol is not None:
        try:
            vol = float(vol)
        except (ValueError, TypeError):
             # If it's not a number, it's invalid
             # However, sometimes it might be None or weird string.
             # If strict_volume is True, this is bad.
             # If not strict, maybe warn?
             # Requirement D: "Reject markets with clearly invalid numeric fields (NaN, negative, absurdly huge)"
             # If it's "100.5", float() handles it. If "NaN", float() handles it (returns nan).
             # If "abc", raises ValueError.
             errors.append(f"Symbol '{symbol}' has invalid volume format: {vol}")
             vol = None

    if vol is not None:
        # Check for NaN
        if vol != vol: # NaN check
             errors.append(f"Symbol '{symbol}' has NaN volume")
        elif vol < 0:
            errors.append(f"Symbol '{symbol}' has negative volume: {vol}")
        elif strict_volume and vol < 1000:
             errors.append(f"Symbol '{symbol}' has low volume: {vol} (STRICT_VOLUME=true)")


def validate_env(markets, expected_env, errors):
    # Confirm dump corresponds to intended DELTA_ENV
    # Delta Exchange has 'info' which might contain URLs or IDs.
    # If not available, log warning.

    # Check first market
    if not markets:
        return

    m = markets[0]
    info = m.get("info", {})

    # Delta specific checks if info is available
    # This is a heuristic.
    # If expected_env is 'india_prod', maybe URL contains 'india.delta.exchange'
    # If 'global_prod', maybe 'delta.exchange'
    # If 'india_testnet', maybe 'testnet'

    # This depends on what CCXT puts in 'info'.
    # Freqtrade's list-markets --print-json dumps the CCXT market structure.

    # We can also check if symbols look right?
    pass

    found_url = ""
    if isinstance(info, dict):
        for k, v in info.items():
            if isinstance(v, str) and "http" in v:
                found_url = v
                break

    if not found_url:
        warn("No URL found in market info to verify environment.")
        return

    # Check against expected env
    # india_prod -> india.delta.exchange
    # global_prod -> delta.exchange (but not india)
    # india_testnet -> testnet

    if expected_env == "india_prod":
        if "india.delta.exchange" not in found_url:
             warn(f"Environment mismatch? Expected {expected_env} but found URL {found_url}")
    elif expected_env == "global_prod":
        if "delta.exchange" not in found_url or "india" in found_url:
             warn(f"Environment mismatch? Expected {expected_env} but found URL {found_url}")
    elif "testnet" in expected_env:
        if "testnet" not in found_url:
             warn(f"Environment mismatch? Expected {expected_env} but found URL {found_url}")


def validate_drift(current_symbols, prev_whitelist_path, max_removal_ratio):
    drift_errors = []
    drift_info = []

    if not prev_whitelist_path or not os.path.exists(prev_whitelist_path):
        drift_info.append("No previous whitelist found. Skipping drift check.")
        return drift_errors, drift_info

    try:
        with open(prev_whitelist_path, "r") as f:
            prev_data = json.load(f)

        # Previous whitelist might be a list of strings (symbols) or freqtrade config format
        if isinstance(prev_data, list):
            prev_symbols = set(prev_data)
        elif isinstance(prev_data, dict) and "pair_whitelist" in prev_data.get("exchange", {}):
            prev_symbols = set(prev_data["exchange"]["pair_whitelist"])
        elif isinstance(prev_data, dict) and "pairs" in prev_data: # simple dict wrapper
             prev_symbols = set(prev_data["pairs"])
        else:
            # Fallback: maybe it's the markets dump?
            # The prompt says "compare newly generated whitelist vs last committed whitelist"
            # So it's likely a list of symbols or a config.
            # Let's assume it's a list of symbols if simple json list, else config.
            # If it fails to parse as expected, warn and skip.
            warn(f"Unknown format for previous whitelist at {prev_whitelist_path}")
            return drift_errors, drift_info

    except Exception as e:
        warn(f"Could not read previous whitelist: {e}")
        return drift_errors, drift_info

    # Filter out inactive pairs from previous if we could?
    # But previous whitelist usually contains only active pairs we wanted to trade.

    # Calculate drift
    removed = prev_symbols - current_symbols
    added = current_symbols - prev_symbols

    # Removal ratio
    if len(prev_symbols) > 0:
        removal_ratio = len(removed) / len(prev_symbols)
    else:
        removal_ratio = 0.0

    drift_info.append(f"Drift stats: +{len(added)} / -{len(removed)} (Ratio: {removal_ratio:.2f})")
    drift_info.append(f"Previous count: {len(prev_symbols)}, Current count: {len(current_symbols)}")

    if removal_ratio > max_removal_ratio:
        drift_errors.append(f"Large delist drift: {removal_ratio:.2f} > {max_removal_ratio}. Manual review required.")
        if removed:
            drift_errors.append(f"Removed pairs sample: {list(removed)[:5]}")

    # Format change check
    # Check if a removed symbol is a substring of an added symbol (or vice versa), flag it as potential format change.
    # Example: BTC/USDT (removed) -> BTC/USDT:USDT (added)

    format_changes = []
    for r in removed:
        for a in added:
            # Check if r is substring of a (BTC/USDT in BTC/USDT:USDT)
            # OR if a is substring of r (unlikely for futures upgrade)
            # OR if they share same base/quote (complex to parse)
            if r in a or a in r:
                 # Check if the change is just the settle delimiter
                 # This is a format change
                 format_changes.append(f"{r} -> {a}")

    if format_changes:
        drift_errors.append(f"Potential format changes detected for {len(format_changes)} pairs.")
        drift_errors.append(f"Format change sample: {format_changes[:5]}")
        # The requirement says "If pair-format changed for any existing pair, FAIL"
        # So we treat this as an error.

    return drift_errors, drift_info


def is_eligible(market, filter_mode, allowlist_regex):
    # Basic active check
    if not market.get("active", True):
        return False

    symbol = market.get("symbol", "")
    if not symbol:
        return False

    # Filter logic
    if filter_mode == "perps_usdt":
        return "/USDT:USDT" in symbol
    elif filter_mode == "all_futures":
        return True # Assuming dump is already filtered by type if requested, but better safe?
        # Actually generate_whitelist just says "all_futures" -> append(symbol)
    elif filter_mode == "allowlist_regex":
        return bool(re.match(allowlist_regex, symbol))
    else:
        # Default to perps_usdt
        return "/USDT:USDT" in symbol


def main():
    parser = argparse.ArgumentParser(description="Validate Market Schema")
    parser.add_argument("--markets", required=True, help="Path to markets.json")
    parser.add_argument("--env", required=True, help="Delta Environment (india_prod, global_prod, india_testnet)")
    parser.add_argument("--prev-whitelist", help="Path to previous whitelist.json")
    parser.add_argument("--out-report", required=True, help="Path to output report.md")

    args = parser.parse_args()

    # Load config from env
    min_markets = int(os.environ.get("MIN_MARKETS", DEFAULT_MIN_MARKETS))
    max_removal_ratio = float(os.environ.get("MAX_REMOVAL_RATIO", DEFAULT_MAX_REMOVAL_RATIO))
    strict_volume = os.environ.get("STRICT_VOLUME", str(DEFAULT_STRICT_VOLUME)).lower() == "true"
    filter_mode = os.environ.get("FILTER_MODE", "perps_usdt")
    allowlist_regex = os.environ.get("ALLOWLIST_REGEX", ".*")

    # Determine strictness based on filter mode
    strict_futures = filter_mode in ["perps_usdt", "all_futures"]

    print(f"Validating {args.markets} for {args.env} (Filter: {filter_mode})...")

    # Load Markets
    try:
        with open(args.markets, "r") as f:
            data = json.load(f)
    except Exception as e:
        fail(f"Invalid JSON in markets file: {e}")

    # Handle structure
    if isinstance(data, dict) and "markets" in data:
        markets = data["markets"]
    elif isinstance(data, list):
        markets = data
    else:
        fail("Root must be a list of markets or dict with 'markets' key")

    # Basic count check
    if len(markets) < min_markets:
        # Write basic report before failing
        fail(f"Market count {len(markets)} < MIN_MARKETS ({min_markets})", args.out_report, f"# FAIL\nMarket count {len(markets)} < MIN_MARKETS ({min_markets})")

    # Validate each market
    symbols = set()
    eligible_symbols = set()
    errors = []

    # Check for duplicate symbols
    # Case insensitive check? Requirement says "case-insensitive symbol uniqueness".
    seen_symbols_lower = {}

    for i, m in enumerate(markets):
        symbol = validate_market_structure(i, m, errors)
        if not symbol:
            continue

        # Only strict format check on ELIGIBLE symbols?
        # Or on all? Requirement: "For each market that will be eligible for whitelist".
        eligible = is_eligible(m, filter_mode, allowlist_regex)

        if eligible:
            validate_symbol_format(symbol, errors, strict_futures=strict_futures)
            eligible_symbols.add(symbol)

        # Check uniqueness on all? Or eligible?
        # Duplicate symbol in dump is bad regardless.
        s_lower = symbol.lower()
        if s_lower in seen_symbols_lower:
             errors.append(f"Duplicate symbol '{symbol}' (conflicts with '{seen_symbols_lower[s_lower]}')")
        seen_symbols_lower[s_lower] = symbol
        symbols.add(symbol)

        validate_numeric(m, symbol, errors, strict_volume)

    # Environment Sanity
    validate_env(markets, args.env, errors)

    # Drift Check (on eligible symbols vs prev whitelist)
    drift_info = []
    if args.prev_whitelist:
        d_errors, drift_info = validate_drift(eligible_symbols, args.prev_whitelist, max_removal_ratio)
        errors.extend(d_errors)

    # Report Generation
    status = "PASS" if not errors else "FAIL"

    report_lines = [
        f"# Markets Schema Validation Report",
        f"Date: {datetime.now(timezone.utc).isoformat()}",
        f"Status: **{status}**",
        f"Env: {args.env}",
        f"File: {args.markets}",
        f"",
        f"## Counts",
        f"- Total Markets: {len(markets)}",
        f"- Unique Symbols: {len(symbols)}",
        f"- Eligible Symbols: {len(eligible_symbols)}",
        f"",
        f"## Drift Analysis",
    ]
    report_lines.extend([f"- {line}" for line in drift_info])

    if errors:
        report_lines.append("")
        report_lines.append("## Errors")
        for e in errors[:20]:
            report_lines.append(f"- {e}")
        if len(errors) > 20:
             report_lines.append(f"- ...and {len(errors) - 20} more")

    report_content = "\n".join(report_lines)

    # Write report
    report_written = False
    try:
        with open(args.out_report, "w") as f:
            f.write(report_content)
        print(f"Report written to {args.out_report}")
        report_written = True
    except Exception as e:
        warn(f"Could not write report: {e}")

    if errors:
        if report_written:
             fail("Validation failed. See report.")
        else:
             # Fallback if report writing failed
             fail(f"Validation failed. Errors:\n" + "\n".join(errors[:10]))

    print("VALIDATION PASS")
    sys.exit(0)

if __name__ == "__main__":
    main()
