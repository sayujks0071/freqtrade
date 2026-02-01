#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path


# Configuration defaults
DEFAULT_MIN_MARKETS = 20
DEFAULT_MAX_REMOVAL_RATIO = 0.25


def parse_args():
    parser = argparse.ArgumentParser(
        description="Validate markets schema and check for drift."
    )
    parser.add_argument("--markets", required=True, help="Path to markets JSON file")
    parser.add_argument(
        "--env", required=True, help="Delta Environment (e.g., india_prod)"
    )
    parser.add_argument(
        "--prev-whitelist", help="Path to previous whitelist file (for drift check)"
    )
    parser.add_argument(
        "--out-report", required=True, help="Path to write the Markdown report"
    )
    return parser.parse_args()


def load_json(path):
    with Path(path).open() as f:
        return json.load(f)


def get_config_vars():
    return {
        "MIN_MARKETS": int(os.environ.get("MIN_MARKETS", DEFAULT_MIN_MARKETS)),
        "MAX_REMOVAL_RATIO": float(
            os.environ.get("MAX_REMOVAL_RATIO", DEFAULT_MAX_REMOVAL_RATIO)
        ),
        "STRICT_VOLUME": os.environ.get("STRICT_VOLUME", "false").lower() == "true",
        "FILTER_MODE": os.environ.get("FILTER_MODE", "perps_usdt"),
        "ALLOWLIST_REGEX": os.environ.get("ALLOWLIST_REGEX", ".*"),
    }


def is_eligible(market, config):
    symbol = market.get("symbol", "")
    active = market.get("active", True)  # Default to True if missing

    if not active:
        return False

    mode = config["FILTER_MODE"]
    regex = re.compile(config["ALLOWLIST_REGEX"])

    if mode == "perps_usdt":
        return "/USDT:USDT" in symbol
    elif mode == "all_futures":
        return True
    elif mode == "allowlist_regex":
        return bool(regex.match(symbol))
    else:
        # Default to perps_usdt
        return "/USDT:USDT" in symbol


def validate_market(m, idx, errors, config):  # noqa: C901
    # This function is now called only for eligible markets

    # Required fields
    required = ["symbol", "base", "quote", "active"]
    # At least one type indicator
    type_indicators = ["type", "contract", "future", "linear", "swap"]

    missing = [f for f in required if f not in m]
    if missing:
        errors.append(f"Market #{idx}: Missing fields {missing}")
        return None

    # Check for at least one type indicator
    has_type = any(k in m for k in type_indicators)
    if not has_type:
        errors.append(f"Market #{idx}: Missing type/contract indicator")

    symbol = m["symbol"]
    if not isinstance(symbol, str):
        errors.append(f"Market #{idx}: Symbol is not a string")
        return None

    # Symbol Format Checks
    # Must match futures style: BASE/QUOTE:SETTLE ... OR a consistent CCXT format
    # Reject whitespace
    if re.search(r"\s", symbol):
        errors.append(f"Symbol '{symbol}' contains whitespace")

    # Reject lowercase base/quote (usually uppercase)
    if not symbol.isupper():
        errors.append(f"Symbol '{symbol}' must be uppercase")

    # Check for Settle delimiter if it looks like a future and we are in perps mode
    if config["FILTER_MODE"] in ["perps_usdt", "all_futures"]:
        pass  # Checked in main loop if needed

    # Numeric checks (Volume)
    if config["STRICT_VOLUME"]:
        # Check volume if available in top-level or info
        vol = m.get("volume")
        if vol is None:
            # Try info
            info = m.get("info", {})
            vol_str = info.get("volume_24h") or info.get("turnover_24h")
            if vol_str is not None:
                try:
                    vol = float(vol_str)
                except ValueError:
                    pass

        if vol is not None and isinstance(vol, (int, float)):
            if vol < 1000:
                errors.append(f"Market {symbol}: Low volume ({vol})")

    return symbol


def check_numeric_sanity(m, idx, errors, config):
    symbol = m.get("symbol", f"#{idx}")

    # Check limits
    if "limits" in m:
        limits = m["limits"]
        # Amount limits
        if "amount" in limits:
            amt = limits["amount"]
            if isinstance(amt, dict):
                min_amt = amt.get("min")
                max_amt = amt.get("max")
                if isinstance(min_amt, (int, float)) and min_amt < 0:
                    errors.append(
                        f"Market {symbol}: Negative min amount limit ({min_amt})"
                    )
                if isinstance(max_amt, (int, float)) and max_amt < 0:
                    errors.append(
                        f"Market {symbol}: Negative max amount limit ({max_amt})"
                    )
                if (
                    isinstance(min_amt, (int, float))
                    and isinstance(max_amt, (int, float))
                    and min_amt > max_amt
                ):
                    errors.append(
                        f"Market {symbol}: Invalid limits (min {min_amt} > max {max_amt})"
                    )

    # Check precision
    if "precision" in m:
        prec = m["precision"]
        if isinstance(prec, dict):
            for k, v in prec.items():
                if isinstance(v, (int, float)) and v < 0:
                    errors.append(f"Market {symbol}: Negative precision for {k}: {v}")

    return


def validate_environment_sanity(markets, env):
    if not markets:
        return
    # first_market = markets[0]
    # info = first_market.get("info", {})
    print(
        "WARN: Environment sanity check limited due to dump format. "
        "Validating based on schema structure only."
    )


def main():  # noqa: C901
    args = parse_args()
    config = get_config_vars()

    # Load Markets
    try:
        data = load_json(args.markets)
    except Exception as e_load:
        print(f"FAIL: Could not load markets JSON: {e_load}")
        sys.exit(2)

    # Handle different list-markets output formats
    markets = []
    if isinstance(data, list):
        markets = data
    elif isinstance(data, dict) and "markets" in data:
        markets = data["markets"]
    else:
        print(
            "FAIL: Invalid markets JSON structure (not a list or dict with 'markets')"
        )
        sys.exit(2)

    # Validation Results
    errors = []
    symbols_seen = set()
    eligible_symbols = []

    # A) Count Check
    if len(markets) < config["MIN_MARKETS"]:
        errors.append(
            f"Total markets count {len(markets)} < MIN_MARKETS ({config['MIN_MARKETS']})"
        )

    # B, C, D) Per-market validation
    for i, m in enumerate(markets):
        # Check eligibility first
        if is_eligible(m, config):
            # Run strict validation
            validated_symbol = validate_market(m, i, errors, config)
            check_numeric_sanity(m, i, errors, config)

            if validated_symbol:
                # Uniqueness
                if validated_symbol.lower() in symbols_seen:
                    errors.append(f"Duplicate symbol '{validated_symbol}'")
                symbols_seen.add(validated_symbol.lower())
                eligible_symbols.append(validated_symbol)

                # Check settle delimiter for eligible perps
                if config["FILTER_MODE"] == "perps_usdt":
                    if ":" not in validated_symbol:
                        errors.append(
                            f"Symbol '{validated_symbol}' eligible but missing settle "
                            "delimiter (:) for perps_usdt mode"
                        )

    # E) Environment Sanity
    validate_environment_sanity(markets, args.env)

    # F) Drift Safety Gate
    drift_errors = []
    drift_stats = {"added": [], "removed": [], "ratio": 0.0, "format_changed": []}
    prev_set = set()

    if args.prev_whitelist and Path(args.prev_whitelist).exists():
        try:
            prev_data = load_json(args.prev_whitelist)
            prev_pairs = []
            if isinstance(prev_data, dict) and "exchange" in prev_data:
                prev_pairs = prev_data.get("exchange", {}).get("pair_whitelist", [])
            elif isinstance(prev_data, list):
                prev_pairs = prev_data

            prev_set = set(prev_pairs)
            curr_set = set(eligible_symbols)

            removed = prev_set - curr_set
            added = curr_set - prev_set

            removal_ratio = (
                len(removed) / len(prev_set) if len(prev_set) > 0 else 0.0
            )

            drift_stats["added"] = sorted(list(added))
            drift_stats["removed"] = sorted(list(removed))
            drift_stats["ratio"] = removal_ratio

            if removal_ratio > config["MAX_REMOVAL_RATIO"]:
                drift_errors.append(
                    f"Large delist drift: {removal_ratio:.2f} > "
                    f"{config['MAX_REMOVAL_RATIO']} (Max allowed). "
                    "Manual review required."
                )

            # Format Change Detection
            def strip_symbol(s):
                return s.split(":")[0]

            removed_stripped = {strip_symbol(s): s for s in removed}
            added_stripped = {strip_symbol(s): s for s in added}

            common_stripped = set(removed_stripped.keys()) & set(added_stripped.keys())

            for common in common_stripped:
                old_sym = removed_stripped[common]
                new_sym = added_stripped[common]
                msg = f"Format change detected: {old_sym} -> {new_sym}"
                drift_stats["format_changed"].append(msg)
                drift_errors.append(msg)

        except Exception as e_drift:
            drift_errors.append(f"Failed to process previous whitelist: {e_drift}")
            print(f"WARN: Drift check error: {e_drift}")
    else:
        print("WARN: No previous whitelist found or provided. Skipping drift check.")

    # Compile Report
    is_fail = len(errors) > 0 or len(drift_errors) > 0
    status = "FAIL" if is_fail else "PASS"

    report_lines = []
    report_lines.append("# Markets Schema Validation Report")
    report_lines.append(f"**Date:** {datetime.now(UTC).isoformat()}")
    report_lines.append(f"**Status:** {status}")
    report_lines.append(f"**Environment:** {args.env}")
    report_lines.append("")
    report_lines.append("## Counts")
    report_lines.append(f"- Total Markets: {len(markets)}")
    report_lines.append(f"- Eligible Markets: {len(eligible_symbols)}")
    report_lines.append(f"- Whitelist Size (Prev): {len(prev_set)}")
    report_lines.append("")

    if drift_stats["ratio"] > 0 or drift_stats["added"] or drift_stats["removed"]:
        report_lines.append("## Drift Summary")
        report_lines.append(f"- Added: {len(drift_stats['added'])}")
        report_lines.append(f"- Removed: {len(drift_stats['removed'])}")
        report_lines.append(f"- Removal Ratio: {drift_stats['ratio']:.2%}")
        if drift_stats["removed"]:
            report_lines.append(
                f"- Sample Removed: {', '.join(drift_stats['removed'][:5])}"
            )
        if drift_stats["format_changed"]:
            report_lines.append(
                f"- Format Changes: {', '.join(drift_stats['format_changed'][:5])}"
            )
        report_lines.append("")

    if errors:
        report_lines.append("## Schema Errors")
        for e in errors[:20]:
            report_lines.append(f"- {e}")
        if len(errors) > 20:
            report_lines.append(f"- ... and {len(errors) - 20} more")
        report_lines.append("")

    if drift_errors:
        report_lines.append("## Drift Errors")
        for e in drift_errors:
            report_lines.append(f"- {e}")
        report_lines.append("")

    # Write Report
    try:
        with Path(args.out_report).open("w") as f:
            f.write("\n".join(report_lines))
        print(f"Report written to {args.out_report}")
    except Exception as e_write:
        print(f"FAIL: Could not write report: {e_write}")
        pass

    if is_fail:
        print("Validation FAILED. See report for details.")
        sys.exit(2)
    else:
        print("Validation PASSED.")
        sys.exit(0)


if __name__ == "__main__":
    main()
