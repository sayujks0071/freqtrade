#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


# Add tools directory to sys.path to allow importing generate_whitelist
current_dir = Path(__file__).parent
sys.path.append(str(current_dir))

try:
    from generate_whitelist import filter_markets
except ImportError:
    # Fallback if running from root without tools in path
    sys.path.append(str(current_dir.parent / "tools"))
    from generate_whitelist import filter_markets


# Configuration defaults
DEFAULT_MIN_MARKETS = 20
DEFAULT_MAX_REMOVAL_RATIO = 0.25

# Env sanity check values
ENV_URLS = {
    "india_prod": ["api.india.delta.exchange", "india.delta.exchange"],
    "global_prod": ["api.delta.exchange", "www.delta.exchange"],
    "india_testnet": [
        "testnet.deltaex.org",
        "testnet.delta.exchange",
        "cdn-ind.testnet.deltaex.org",
    ],
}


class ValidationFailure(Exception):
    def __init__(self, message, stats=None, drift_info=None, errors=None):
        self.message = message
        self.stats = stats or (0, 0, 0)
        self.drift_info = drift_info or ([], 0.0, 0, 0)
        self.errors = errors or []
        super().__init__(message)


def warn(message):
    print(f"WARN: {message}")


def validate_environment(data, env):
    """
    Checks if the dump corresponds to the intended DELTA_ENV.
    """
    if not env or env not in ENV_URLS:
        warn(f"Unknown or missing DELTA_ENV: {env}. Skipping environment sanity check.")
        return

    expected_domains = ENV_URLS[env]

    # Check if 'urls' exists in the top-level dict
    if isinstance(data, dict) and "urls" in data:
        urls = data["urls"]
        found_match = False

        # Flatten urls values to string to search
        urls_str = str(urls)

        for domain in expected_domains:
            if domain in urls_str:
                found_match = True
                break

        if not found_match:
            warn(
                f"Environment mismatch? DELTA_ENV={env} expects domains {expected_domains}, "
                f"but found none in 'urls' metadata."
            )
    else:
        # If input is just a list of markets, we can't check exchange metadata
        warn(
            "Input data does not contain exchange metadata (urls). "
            "Skipping environment sanity check."
        )


def validate_market_structure(i, m, errors):
    required_fields = ["symbol", "base", "quote", "active"]
    type_fields = ["type", "contract", "linear", "inverse", "future", "swap"]

    for f in required_fields:
        if f not in m:
            errors.append(f"Item {i} missing field '{f}'")

    has_type = any(f in m for f in type_fields)
    if not has_type:
        errors.append(f"Item {i} ({m.get('symbol', 'unknown')}) missing type/contract indicator")

    symbol = m.get("symbol", "")
    if not symbol:
        errors.append(f"Item {i} has empty symbol")
        return None
    return symbol


def validate_symbol_format(symbol, errors):
    # Symbol format: BASE/QUOTE:SETTLE for futures usually
    if re.search(r"\s", symbol):
        errors.append(f"Symbol '{symbol}' contains whitespace")
    if symbol != symbol.upper():
        errors.append(f"Symbol '{symbol}' is not uppercase")

    if ":" not in symbol:
        errors.append(f"Symbol '{symbol}' missing settle delimiter (:)")


def validate_volume(m, symbol, strict_volume, errors):
    if "limits" in m:
        limits = m["limits"]
        if isinstance(limits, dict):
            for k, v in limits.items():
                if isinstance(v, dict):
                    for subk, subv in v.items():
                        if isinstance(subv, (int, float)) and subv < 0:
                            errors.append(
                                f"Symbol '{symbol}' has negative limit {k}.{subk}: {subv}"
                            )

    # Optional strict volume check (e.g. check 24h volume if available)
    # Since 'list-markets' might not provide volume, we skip unless we find it.
    if "info" in m and isinstance(m["info"], dict):
        # Check for common volume keys in info (Delta usually returns 24h volume in info)
        vol = m["info"].get("volume_24h") or m["info"].get("quote_volume_24h")

        if vol is not None:
            try:
                vol_float = float(vol)
                if vol_float < 1000:
                    msg = f"Symbol '{symbol}' volume {vol_float} < 1000"
                    if strict_volume:
                        errors.append(msg)
                    else:
                        print(f"WARN: {msg}")
            except (ValueError, TypeError):
                pass


def validate_schema(data, min_markets, strict_volume):  # noqa: C901
    markets_list = []
    if isinstance(data, list):
        markets_list = data
    elif isinstance(data, dict) and "markets" in data:
        if isinstance(data["markets"], dict):
            markets_list = list(data["markets"].values())
        elif isinstance(data["markets"], list):
            markets_list = data["markets"]
    elif isinstance(data, dict):
        first_val = next(iter(data.values())) if data else None
        if isinstance(first_val, dict) and "symbol" in first_val:
            markets_list = list(data.values())

    if not markets_list:
        raise ValidationFailure("Could not find markets list in input data")

    # Filter eligible markets
    eligible_symbols = set(filter_markets(markets_list))
    eligible_markets = [m for m in markets_list if m.get("symbol") in eligible_symbols]

    total_count = len(markets_list)
    eligible_count = len(eligible_markets)

    if eligible_count < min_markets:
        raise ValidationFailure(
            f"Eligible market count {eligible_count} < MIN_MARKETS ({min_markets})",
            stats=(total_count, eligible_count, 0),
        )

    symbols = set()
    errors = []

    for i, m in enumerate(eligible_markets):
        symbol = validate_market_structure(i, m, errors)
        if not symbol:
            continue

        validate_symbol_format(symbol, errors)
        validate_volume(m, symbol, strict_volume, errors)

        if symbol.upper() in symbols:
            errors.append(f"Duplicate symbol '{symbol}'")
        symbols.add(symbol.upper())

    if errors:
        raise ValidationFailure(
            "Schema errors found",
            stats=(total_count, eligible_count, len(symbols)),
            errors=errors,
        )

    return symbols, total_count, eligible_count, errors


def validate_drift(current_symbols, previous_path, max_removal_ratio):
    prev_path_obj = Path(previous_path)
    if not previous_path or not prev_path_obj.exists():
        print("No previous whitelist found. Skipping drift check.")
        return [], 0.0, 0, 0  # removed, ratio, added_count, prev_count

    try:
        with prev_path_obj.open() as f:
            prev_data = json.load(f)
            if "exchange" in prev_data and "pair_whitelist" in prev_data["exchange"]:
                prev_symbols = set(prev_data["exchange"]["pair_whitelist"])
            elif isinstance(prev_data, list):
                prev_symbols = set(prev_data)
            else:
                warn("Previous whitelist format unrecognized. Skipping drift check.")
                return [], 0.0, 0, 0
    except Exception as e:
        warn(f"Could not read previous whitelist: {e}")
        return [], 0.0, 0, 0

    if not prev_symbols:
        return [], 0.0, 0, 0

    removed = prev_symbols - current_symbols
    added = current_symbols - prev_symbols

    removal_ratio = len(removed) / len(prev_symbols)

    print(f"Drift stats: +{len(added)} / -{len(removed)} (Ratio: {removal_ratio:.2f})")

    drift_info = (list(removed), removal_ratio, len(added), len(prev_symbols))

    if removal_ratio > max_removal_ratio:
        raise ValidationFailure(
            f"Large delist drift — manual review required! "
            f"Removal ratio {removal_ratio:.2f} > MAX_REMOVAL_RATIO ({max_removal_ratio}).",
            stats=(
                0,
                0,
                len(current_symbols),
            ),  # We don't have total/eligible here easily
            drift_info=drift_info,
        )

    return drift_info


def write_report(path, status, stats, errors, drift_info, args, message=None):
    (total_markets, eligible_count, whitelist_count) = stats
    (removed_list, removal_ratio, added_count, prev_count) = drift_info

    error_section = ""
    if errors:
        error_section = "## Validation Errors\n\n" + "\n".join([f"- {e}" for e in errors])

    if message and status == "FAIL":
        error_section = f"## FAILURE REASON\n\n**{message}**\n\n" + error_section

    drift_section = "## Drift Analysis\n\n"
    drift_section += f"- Previous Whitelist Size: {prev_count}\n"
    drift_section += f"- Added Pairs: {added_count}\n"
    drift_section += f"- Removed Pairs: {len(removed_list)}\n"
    drift_section += f"- Removal Ratio: {removal_ratio:.2f} (Max: {args.max_removal_ratio})\n"

    if removed_list:
        drift_section += "\n### Removed Pairs (Sample)\n"
        for p in removed_list[:10]:
            drift_section += f"- {p}\n"
        if len(removed_list) > 10:
            drift_section += f"... and {len(removed_list) - 10} more\n"

    # Fix UP017 by using variable outside f-string
    now_iso = datetime.now(timezone.utc).isoformat()  # noqa: UP017

    report = f"""# Markets Schema Validation Report

**Date:** {now_iso}
**Status:** {status}
**File:** {args.markets}
**Environment:** {args.env}

## Counts
- Total Markets in Dump: {total_markets}
- Eligible Markets (Schema Checked): {eligible_count}
- Final Whitelist Size: {whitelist_count}

{drift_section}

{error_section}
"""
    try:
        output_path = Path(args.out_report)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w") as f:
            f.write(report)
        print(f"Report written to {args.out_report}")
    except Exception as e:
        warn(f"Could not write report: {e}")


def main():
    parser = argparse.ArgumentParser(description="Validate Delta Markets Schema")
    parser.add_argument("--markets", required=True, help="Path to markets JSON dump")
    parser.add_argument("--env", required=True, help="Delta Environment (e.g. india_prod)")
    parser.add_argument("--prev-whitelist", help="Path to previous whitelist JSON")
    parser.add_argument("--out-report", required=True, help="Path to output markdown report")

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

    args = parser.parse_args()

    print(f"Validating {args.markets} for {args.env}...")

    stats = (0, 0, 0)
    drift_info = ([], 0.0, 0, 0)

    try:
        with Path(args.markets).open() as f:
            data = json.load(f)

        # Environment Sanity
        validate_environment(data, args.env)

        # Schema Validation
        symbols, total_count, eligible_count, errors = validate_schema(
            data, args.min_markets, args.strict_volume
        )
        stats = (total_count, eligible_count, len(symbols))

        # Drift Check
        drift_info = validate_drift(symbols, args.prev_whitelist, args.max_removal_ratio)

        write_report(args.out_report, "PASS", stats, errors, drift_info, args)
        print("VALIDATION PASS")

    except ValidationFailure as e:
        print(f"FAIL: {e.message}")
        # Use stats from exception if available, otherwise what we have
        final_stats = e.stats if e.stats != (0, 0, 0) else stats
        # If drift caused failure, we might have drift info
        final_drift = e.drift_info if e.drift_info != ([], 0.0, 0, 0) else drift_info
        final_errors = e.errors if e.errors else []

        write_report(
            args.out_report,
            "FAIL",
            final_stats,
            final_errors,
            final_drift,
            args,
            message=e.message,
        )
        sys.exit(2)

    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        # Try to write a crash report
        try:
            write_report(
                args.out_report,
                "CRASH",
                stats,
                [str(e)],
                drift_info,
                args,
                message="Script Crashed",
            )
        except Exception:  # noqa: S110
            pass
        sys.exit(2)


if __name__ == "__main__":
    main()
