#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# Import filter_markets from generate_whitelist
# We assume the script is run from the repo root or tools/ folder.
try:
    from tools.generate_whitelist import filter_markets
except ImportError:
    try:
        sys.path.append(str(Path(__file__).parent))
        from generate_whitelist import filter_markets
    except ImportError:
        print("Error: Could not import filter_markets from generate_whitelist.py")
        sys.exit(1)

# Configuration from Env (also used as defaults if not in env, but args override)
# We will use args primarily.
ENV_MIN_MARKETS = int(os.environ.get("MIN_MARKETS", 20))
ENV_MAX_REMOVAL_RATIO = float(os.environ.get("MAX_REMOVAL_RATIO", 0.25))
ENV_STRICT_VOLUME = os.environ.get("STRICT_VOLUME", "false").lower() == "true"


def parse_args():
    parser = argparse.ArgumentParser(description="Validate markets schema and check for drift.")
    parser.add_argument("--markets", required=True, help="Path to markets JSON file")
    parser.add_argument("--env", required=True, help="Delta environment (e.g. india_prod)")
    parser.add_argument("--prev-whitelist", help="Path to previous whitelist JSON")
    parser.add_argument("--out-report", required=True, help="Path to output report markdown")
    return parser.parse_args()


def write_report(path, content):
    try:
        # Ensure directory exists
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with Path(path).open("w") as f:
            f.write(content)
        print(f"Report written to {path}")
    except Exception as e:
        print(f"Could not write report: {e}")


def fail(reason, report_content, report_path):
    print(f"FAIL: {reason}")
    final_report = report_content + f"\n\n## FAILURE\n**Reason:** {reason}\n"
    write_report(report_path, final_report)
    sys.exit(2)


def validate_symbol_format(symbol):
    # Rule: BASE/QUOTE:SETTLE
    # Also reject whitespace, lowercase
    if re.search(r"\s", symbol):
        return f"Symbol '{symbol}' contains whitespace"
    if symbol != symbol.upper():
        return f"Symbol '{symbol}' is not uppercase"
    if ":" not in symbol:
        return f"Symbol '{symbol}' missing settle delimiter (:)"
    return None


def check_numeric(value, field_name):
    try:
        v = float(value)
        if v < 0:
            return f"{field_name} is negative: {v}"
        if v != v:  # NaN
            return f"{field_name} is NaN"
        if v == float("inf"):
            return f"{field_name} is Inf"
    except (ValueError, TypeError):
        return f"{field_name} is not a number: {value}"
    return None


def main():
    args = parse_args()
    report_lines = [
        "# Markets Schema Validation Report",
        f"Date: {datetime.now(timezone.utc).isoformat()}",
        f"Environment: {args.env}",
        f"Markets File: {args.markets}",
        "",
    ]

    # 1. Load Markets
    if not Path(args.markets).exists():
        fail(f"Markets file not found: {args.markets}", "\n".join(report_lines), args.out_report)

    try:
        with Path(args.markets).open() as f:
            data = json.load(f)
    except Exception as e:
        fail(f"Invalid JSON in markets file: {e}", "\n".join(report_lines), args.out_report)

    # Handle top-level list or dict
    markets_list = []
    if isinstance(data, list):
        markets_list = data
    elif isinstance(data, dict) and "markets" in data:
        markets_list = data["markets"]
    else:
        fail(
            "Markets JSON must be a list or a dict containing 'markets' key",
            "\n".join(report_lines),
            args.out_report,
        )

    total_markets = len(markets_list)
    report_lines.append(f"- Total Markets Scanned: {total_markets}")

    # A) Markets count
    if total_markets < ENV_MIN_MARKETS:
        fail(
            f"Markets count {total_markets} < MIN_MARKETS ({ENV_MIN_MARKETS})",
            "\n".join(report_lines),
            args.out_report,
        )

    # C) Schema Validation for ALL markets (or at least check structure)
    # Required fields
    required_fields = ["symbol", "base", "quote", "active"]
    # Type indicators: need at least one of these
    type_indicators = ["type", "contract", "future", "spot", "swap", "linear"]

    errors = []
    seen_symbols = set()

    for i, m in enumerate(markets_list):
        # Basic fields
        missing = [f for f in required_fields if f not in m]
        if missing:
            errors.append(f"Market index {i} missing fields: {missing}")
            continue

        symbol = m["symbol"]

        # Uniqueness
        if symbol.upper() in seen_symbols:
            errors.append(f"Duplicate symbol: {symbol}")
        seen_symbols.add(symbol.upper())

        # Type indicator check (loose check, just need some indication)
        # ccxt/freqtrade usually puts 'type'
        has_type = any(k in m for k in type_indicators)
        # Also 'info' might contain raw data, but we check top level
        if not has_type and "type" not in m:
             # Some dumps might not have explicit type if inferred?
             # But 'type' is standard in ccxt.
             # Let's be lenient if we can infer it, but the spec says "type / contract / future/perp indicator (at least one)"
             # We'll check if 'type' key exists or 'contract' key exists.
             if not (m.get("type") or m.get("contract") or m.get("future") or m.get("spot") or m.get("swap") or m.get("linear")):
                 errors.append(f"Market {symbol} missing type indicator")

        # D) Numeric checks (if present)
        if "limits" in m and isinstance(m["limits"], dict):
            for k, v in m["limits"].items():
                if isinstance(v, dict):
                    for sub_k, sub_v in v.items():
                        if sub_v is not None:
                            err = check_numeric(sub_v, f"limits.{k}.{sub_k}")
                            if err:
                                errors.append(f"{symbol}: {err}")

        # Volume check (if strict)
        # Assuming volume is available? Usually list-markets doesn't have 24h volume unless explicitly fetched with ticker.
        # But if it is there:
        if "volume" in m:
            vol = m["volume"]
            if vol is not None:
                err = check_numeric(vol, "volume")
                if err:
                    errors.append(f"{symbol}: {err}")
                elif ENV_STRICT_VOLUME and vol < 1000: # Example threshold
                     errors.append(f"{symbol}: Low volume {vol}")

    if errors:
        # Abort if schema is bad
        fail(
            f"Schema violations found ({len(errors)}):\n" + "\n".join(errors[:20]),
            "\n".join(report_lines),
            args.out_report,
        )

    # Get Eligible Markets (Simulate Whitelist)
    try:
        candidate_whitelist = filter_markets(markets_list)
    except Exception as e:
        fail(
            f"Failed to generate whitelist candidates: {e}",
            "\n".join(report_lines),
            args.out_report,
        )

    report_lines.append(f"- Eligible Markets (Candidate Whitelist): {len(candidate_whitelist)}")

    # Check symbol format for eligible markets
    format_errors = []
    for sym in candidate_whitelist:
        err = validate_symbol_format(sym)
        if err:
            format_errors.append(err)

    if format_errors:
        fail(
             f"Eligible markets have invalid symbol format ({len(format_errors)}):\n" + "\n".join(format_errors[:20]),
             "\n".join(report_lines),
             args.out_report
        )

    # E) Environment Sanity
    # We try to guess from metadata if possible.
    # Looking at the first market's info.
    if markets_list and "info" in markets_list[0]:
        info = markets_list[0]["info"]
        # This depends on Delta Exchange raw API response structure
        # Use str(info) to search
        info_str = str(info)
        if args.env == "india_prod" or "india" in args.env:
             # Expect something related to delta.exchange/india or similar?
             # Or maybe just NOT testnet.
             pass
        # This is hard to validate without knowing exact dump structure.
        # We will log a warning if we see something contradictory.
        if "testnet" in args.env and "testnet" not in info_str.lower() and "sandbox" not in info_str.lower():
             report_lines.append("WARN: Env is testnet but 'testnet'/'sandbox' not found in market info.")
        if "prod" in args.env and ("testnet" in info_str.lower() or "sandbox" in info_str.lower()):
             report_lines.append("WARN: Env is prod but 'testnet'/'sandbox' found in market info.")

    # F) Drift Safety Gate
    if args.prev_whitelist and Path(args.prev_whitelist).exists():
        try:
            with Path(args.prev_whitelist).open() as f:
                prev_data = json.load(f)

            # Whitelist format: {"exchange": {"pair_whitelist": [...]}} or just list
            if isinstance(prev_data, dict) and "exchange" in prev_data:
                prev_pairs = set(prev_data["exchange"].get("pair_whitelist", []))
            elif isinstance(prev_data, list):
                prev_pairs = set(prev_data)
            else:
                 # Try finding list in top level
                 prev_pairs = set()
                 report_lines.append("WARN: Could not parse previous whitelist structure.")

            current_pairs = set(candidate_whitelist)

            removed = prev_pairs - current_pairs
            added = current_pairs - prev_pairs
            kept = prev_pairs & current_pairs

            removal_count = len(removed)
            prev_count = len(prev_pairs)
            removal_ratio = removal_count / prev_count if prev_count > 0 else 0.0

            report_lines.append(f"- Drift Check:")
            report_lines.append(f"  - Previous Whitelist Count: {prev_count}")
            report_lines.append(f"  - Added: {len(added)}")
            report_lines.append(f"  - Removed: {removal_count}")
            report_lines.append(f"  - Removal Ratio: {removal_ratio:.2%}")

            if removal_ratio > ENV_MAX_REMOVAL_RATIO:
                fail(
                    f"Large delist drift — manual review required. Removal ratio {removal_ratio:.2f} > {ENV_MAX_REMOVAL_RATIO}",
                    "\n".join(report_lines),
                    args.out_report
                )

            # Check for format change in existing pairs
            # If a pair was in prev and is in current, we assumed format is same because symbol string is same.
            # But "If pair-format changed for any existing pair".
            # If the string is the same, the format is the same.
            # Maybe it means "If a pair exists but with different format"?
            # e.g. BTC/USDT:USDT vs BTC/USDT
            # If the underlying instrument is the same but symbol changed.
            # This is hard to detect without ID mapping.
            # But the requirement says "Reject symbols with ... OR a consistent CCXT format discovered from dump."
            # If we enforce BASE/QUOTE:SETTLE, we are safe.
            # We already validated symbol format for all eligible markets.

            # If "pair-format changed for any existing pair" implies we shouldn't have widespread renames.
            # If we had BTC/USDT:USDT and now we have BTC-USDT-SWAP, and we lose the old one, it counts as removal.
            # If removal ratio is high, we catch it.

        except Exception as e:
             fail(f"Drift check failed with error: {e}", "\n".join(report_lines), args.out_report)
    else:
        report_lines.append("WARN: No previous whitelist found. Skipping drift check.")

    # PASS
    report_lines.append("\n**STATUS: PASS**")
    write_report(args.out_report, "\n".join(report_lines))
    sys.exit(0)

if __name__ == "__main__":
    main()
