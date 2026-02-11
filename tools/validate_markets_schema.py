#!/usr/bin/env python3
import argparse
import json
import math
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

# Add repo root to sys.path to allow imports if running from tools/ or root
try:
    from tools.generate_whitelist import filter_markets
except ImportError:
    # If run from tools dir, add parent
    sys.path.append(str(Path(__file__).resolve().parent))
    try:
        from generate_whitelist import filter_markets
    except ImportError:
        # Fallback if running from root without tools as package
        sys.path.append(str(Path(__file__).resolve().parent.parent))
        from tools.generate_whitelist import filter_markets


# Configuration Defaults
DEFAULT_MIN_MARKETS = 20
DEFAULT_MAX_REMOVAL_RATIO = 0.25


def validate_market_structure(i, m, errors):
    required_fields = ["symbol", "base", "quote", "active"]
    missing = [f for f in required_fields if f not in m]
    if missing:
        errors.append(f"Item {i} missing fields: {', '.join(missing)}")

    # Check for type/contract indicator
    type_indicators = ["type", "contract", "future", "perp", "swap", "linear"]
    has_type = any(k in m for k in type_indicators)

    # Also check 'info' for raw data which might contain type info
    if not has_type and "info" in m and isinstance(m["info"], dict):
        # Some exchanges put type in info
        has_type = any(k in m["info"] for k in type_indicators)

    if not has_type:
        errors.append(f"Item {i} ({m.get('symbol', 'unknown')}) missing type/contract indicator")

    symbol = m.get("symbol", "")
    if not symbol:
        errors.append(f"Item {i} has empty symbol")
        return None
    return symbol


def validate_symbol_format(symbol, errors):
    if re.search(r"\s", symbol):
        errors.append(f"Symbol '{symbol}' contains whitespace")
    if symbol != symbol.upper():
        errors.append(f"Symbol '{symbol}' is not uppercase")

    # Strict check for futures format (must have settle currency)
    if ":" not in symbol:
        errors.append(f"Symbol '{symbol}' missing settle delimiter (:)")

    parts = symbol.split("/")
    if len(parts) != 2:
        errors.append(f"Symbol '{symbol}' invalid structure (missing /)")


def validate_numeric_sanity(m, symbol, strict_volume, errors):
    # Check limits if they exist
    if "limits" in m and isinstance(m["limits"], dict):
        limits = m["limits"]
        for k, v in limits.items():
            if isinstance(v, dict):
                for bound in ["min", "max"]:
                    val = v.get(bound)
                    if val is not None:
                        if not isinstance(val, (int, float)):
                            continue
                        if math.isnan(val) or math.isinf(val) or val < 0:
                            errors.append(f"Symbol '{symbol}' has invalid limit {k}.{bound}: {val}")

    # Volume check (if present top-level)
    if strict_volume and "volume" in m:
        vol = m.get("volume")
        if (
            isinstance(vol, (int, float)) and vol < 1000
        ):  # Arbitrary low threshold? Prompt says "warn by default; allow STRICT_VOLUME=true to fail"
            errors.append(f"Symbol '{symbol}' has low volume: {vol}")


def validate_schema(data, min_markets, strict_volume):
    errors = []

    if not isinstance(data, list):
        errors.append("Root must be a list of markets")
        return set(), errors

    if len(data) < min_markets:
        errors.append(f"Market count {len(data)} < MIN_MARKETS ({min_markets})")

    symbols = set()

    for i, m in enumerate(data):
        symbol = validate_market_structure(i, m, errors)
        if not symbol:
            continue

        # Eligibility check: we only strictly validate active markets or whitelisted ones?
        # Requirement: "For each market that will be eligible for whitelist: Required fields..."
        # So inactive markets can be skipped for strict checks?
        if m.get("active", True):
            validate_symbol_format(symbol, errors)
            validate_numeric_sanity(m, symbol, strict_volume, errors)

        # Uniqueness
        if symbol in symbols:
            errors.append(f"Duplicate symbol '{symbol}'")
        symbols.add(symbol)

    return symbols, errors


def validate_environment(data, env_name, errors):
    # Try to verify environment from dump metadata
    found_metadata = False
    exchange_id = None

    if isinstance(data, dict):
        # Check for top-level exchange info if available
        # This depends heavily on freqtrade --print-json output structure
        if "exchange_id" in data:
            exchange_id = data["exchange_id"]
            found_metadata = True
        elif "info" in data and isinstance(data["info"], dict):
            # Maybe in info?
            exchange_id = data["info"].get("id") or data["info"].get("name")
            found_metadata = True

    if found_metadata and exchange_id:
        print(f"INFO: Detected Exchange ID: {exchange_id}")
        # Heuristic check
        if "india" in env_name.lower() and "india" not in str(exchange_id).lower():
            print(
                f"WARN: Environment mismatch? Expected India env ({env_name}), "
                f"got exchange_id: {exchange_id}"
            )
        elif "global" in env_name.lower() and "india" in str(exchange_id).lower():
            print(
                f"WARN: Environment mismatch? Expected Global env ({env_name}), "
                f"got exchange_id: {exchange_id}"
            )
    else:
        print("WARN: Environment check skipped (no recognizable exchange metadata in dump).")


def validate_drift(current_whitelist_symbols, prev_whitelist_path, max_removal_ratio, errors):
    prev_path_obj = Path(prev_whitelist_path)
    if not prev_whitelist_path or not prev_path_obj.exists():
        print("No previous whitelist found. Skipping drift check.")
        return [], 0.0

    try:
        with prev_path_obj.open() as f:
            prev_data = json.load(f)
            if (
                isinstance(prev_data, dict)
                and "exchange" in prev_data
                and "pair_whitelist" in prev_data["exchange"]
            ):
                prev_symbols = set(prev_data["exchange"]["pair_whitelist"])
            elif isinstance(prev_data, list):
                prev_symbols = set(prev_data)
            else:
                errors.append("Previous whitelist format unrecognized.")
                return [], 0.0
    except Exception as e:
        errors.append(f"Could not read previous whitelist: {e}")
        return [], 0.0

    current_set = set(current_whitelist_symbols)
    removed = prev_symbols - current_set
    added = current_set - prev_symbols

    # Avoid division by zero
    removal_ratio = len(removed) / len(prev_symbols) if len(prev_symbols) > 0 else 0.0

    print(f"Drift stats: +{len(added)} / -{len(removed)} (Ratio: {removal_ratio:.2f})")

    if removal_ratio > max_removal_ratio:
        errors.append(
            f"Large delist drift: {removal_ratio:.2f} > MAX ({max_removal_ratio}). "
            "Manual review required."
        )

    # Check for format changes
    # Heuristic: if a symbol was removed but a very similar one was added
    # (e.g. BTC/USDT -> BTC/USDT:USDT)
    format_changes = []
    for rem in removed:
        base_quote = rem.split(":")[0]
        # Check if any added symbol starts with this base_quote and has a semicolon (new format)
        potential_matches = [a for a in added if a.startswith(base_quote + ":")]
        if potential_matches:
            format_changes.append(f"{rem} -> {potential_matches[0]}")

    if format_changes:
        errors.append(
            f"Format changed for {len(format_changes)} pairs: {', '.join(format_changes[:5])}..."
        )

    return list(removed), removal_ratio


def write_report(path, status, markets_count, whitelist_count, errors, drift_info, args):
    report = f"""# Markets Schema Validation Report
Date: {datetime.now(UTC).isoformat()}
Status: {status}
File: {args.markets}
Environment: {args.env}

## Counts
- Total Markets: {markets_count}
- Whitelist Size: {whitelist_count}

## Drift Analysis
- Removed Pairs: {len(drift_info.get("removed", []))}
- Removal Ratio: {drift_info.get("ratio", 0.0):.2f}
"""

    if errors:
        report += "\n## Errors\n"
        for e in errors:
            report += f"- {e}\n"

    if drift_info.get("removed"):
        report += "\n## Removed Pairs\n"
        for p in drift_info["removed"]:
            report += f"- {p}\n"

    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w") as f:
            f.write(report)
        print(f"Report written to {path}")
    except Exception as e:
        print(f"WARN: Could not write report: {e}")


def main():
    parser = argparse.ArgumentParser(description="Validate markets schema and check for drift.")
    parser.add_argument("--markets", required=True, help="Path to markets JSON dump")
    parser.add_argument("--env", required=True, help="Environment name (e.g., india_prod)")
    parser.add_argument("--prev-whitelist", help="Path to previous whitelist JSON")
    parser.add_argument("--out-report", required=True, help="Path to output markdown report")

    # Env vars for thresholds
    parser.add_argument(
        "--min-markets",
        type=int,
        default=int(os.environ.get("MIN_MARKETS", DEFAULT_MIN_MARKETS)),
    )
    parser.add_argument(
        "--max-removal-ratio",
        type=float,
        default=float(os.environ.get("MAX_REMOVAL_RATIO", DEFAULT_MAX_REMOVAL_RATIO)),
    )
    parser.add_argument(
        "--strict-volume",
        action="store_true",
        default=os.environ.get("STRICT_VOLUME", "false").lower() == "true",
    )

    # Filter mode for whitelist generation
    parser.add_argument(
        "--filter-mode", default=os.environ.get("FILTER_MODE", "perps_usdt")
    )
    parser.add_argument(
        "--allowlist-regex", default=os.environ.get("ALLOWLIST_REGEX", ".*")
    )

    args = parser.parse_args()

    print(f"Validating {args.markets} for env {args.env}...")

    try:
        with Path(args.markets).open() as f:
            data = json.load(f)
    except Exception as e:
        print(f"FAIL: Invalid JSON: {e}")
        # Write minimal failure report
        write_report(args.out_report, "FAIL", 0, 0, [f"Invalid JSON: {e}"], {}, args)
        sys.exit(2)

    # Handle different dump formats
    markets_list = []
    if isinstance(data, dict):
        if "markets" in data:
            markets_list = data["markets"]
        else:
            markets_list = list(data.values()) if data else []
    elif isinstance(data, list):
        markets_list = data
    else:
        print("FAIL: Root must be a list or dict")
        sys.exit(2)

    all_errors = []

    # 1. Validate Schema
    _, schema_errors = validate_schema(
        markets_list, args.min_markets, args.strict_volume
    )
    all_errors.extend(schema_errors)

    # 2. Environment Sanity (Optional/Info)
    validate_environment(data, args.env, all_errors)

    # 3. Drift Safety
    # Generate candidate whitelist
    candidate_whitelist = filter_markets(
        markets_list, filter_mode=args.filter_mode, allowlist_regex=args.allowlist_regex
    )

    drift_info = {"removed": [], "ratio": 0.0}
    if args.prev_whitelist:
        removed, ratio = validate_drift(
            candidate_whitelist,
            args.prev_whitelist,
            args.max_removal_ratio,
            all_errors,
        )
        drift_info["removed"] = removed
        drift_info["ratio"] = ratio

    status = "FAIL" if all_errors else "PASS"

    write_report(
        args.out_report,
        status,
        len(markets_list),
        len(candidate_whitelist),
        all_errors,
        drift_info,
        args,
    )

    if status == "FAIL":
        print(f"Validation FAILED with {len(all_errors)} errors.")
        sys.exit(2)
    else:
        print("Validation PASSED.")
        sys.exit(0)


if __name__ == "__main__":
    main()
