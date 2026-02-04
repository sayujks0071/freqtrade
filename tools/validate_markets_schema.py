#!/usr/bin/env python3
import argparse
import json
import re
import sys
from pathlib import Path


def validate(  # noqa: C901
    markets_file,
    min_markets,
    max_removal_ratio,
    strict_volume,
    prev_whitelist_file,
    out_report,
    env,
):
    report = []
    success = True

    # Load markets
    try:
        with Path(markets_file).open() as f:
            markets_data = json.load(f)
            # Support both list and dict (ccxt structure)
            if isinstance(markets_data, dict):
                markets = list(markets_data.values())
            else:
                markets = markets_data
    except Exception as e:
        msg = f"FAIL: Could not load markets file: {e}"
        print(msg)
        if out_report:
            with Path(out_report).open("w") as f:
                f.write(msg)
        return False

    # Check environment sanity (if possible)
    # Check if markets seem to match the expected env?
    # e.g. check a known pair or URL if available in info

    # Check min markets
    if len(markets) < min_markets:
        msg = f"FAIL: Too few markets: {len(markets)} < {min_markets}"
        print(msg)
        report.append(msg)
        success = False
    else:
        report.append(f"PASS: Market count {len(markets)} >= {min_markets}")

    # Schema checks
    valid_pairs = []
    seen_symbols = set()

    for m in markets:
        symbol = m.get("symbol")
        if not symbol:
            continue

        if symbol in seen_symbols:
            msg = f"FAIL: Duplicate symbol {symbol}"
            print(msg)
            report.append(msg)
            success = False
        seen_symbols.add(symbol)

        # Check format BASE/QUOTE:SETTLE
        # Delta futures usually have this format in CCXT.
        if not re.match(r"^[A-Z0-9]+/[A-Z0-9]+:[A-Z0-9]+$", symbol):
            msg = f"FAIL: Invalid symbol format {symbol}. Expected BASE/QUOTE:SETTLE"
            print(msg)
            report.append(msg)
            success = False

        # Check keys
        required = ["symbol", "base", "quote", "active"]
        if not all(k in m for k in required):
            msg = f"FAIL: Missing required fields in {symbol}"
            print(msg)
            report.append(msg)
            success = False

        if m.get("active") is True:
            valid_pairs.append(symbol)

            # Volume check (if strict)
            # Need to know where volume is. 'info' usually has raw data.
            # CCXT usually normalizes volume in 'quoteVolume' or 'baseVolume' (24h).
            # If strict volume is on, we fail if any active pair has 0 volume?
            # Or just warn? "fail if STRICT_VOLUME=true and too illiquid"
            if strict_volume:
                vol = m.get("quoteVolume")
                if vol is not None and vol < 1000:  # Arbitrary threshold 1000 USD
                    msg = f"FAIL: Low volume for {symbol}: {vol}"
                    print(msg)
                    report.append(msg)
                    success = False

    # Drift check
    if prev_whitelist_file and Path(prev_whitelist_file).exists():
        try:
            with Path(prev_whitelist_file).open() as f:
                prev_pairs = set(json.load(f))

            current_pairs = set(valid_pairs)
            removed = prev_pairs - current_pairs
            removal_ratio = len(removed) / len(prev_pairs) if len(prev_pairs) > 0 else 0

            if removal_ratio > max_removal_ratio:
                msg = (
                    f"FAIL: Removal ratio {removal_ratio:.2f} > {max_removal_ratio}. "
                    f"Removed: {removed}"
                )
                print(msg)
                report.append(msg)
                success = False
            else:
                report.append(f"PASS: Removal ratio {removal_ratio:.2f} <= {max_removal_ratio}")
        except Exception as e:
            report.append(f"WARN: Could not load previous whitelist for drift check: {e}")

    # Write report
    if out_report:
        with Path(out_report).open("w") as f:
            f.write("\n".join(report))

    return success


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--markets", required=True)
    parser.add_argument("--min-markets", type=int, default=20)
    parser.add_argument("--max-removal-ratio", type=float, default=0.25)
    parser.add_argument("--strict-volume", action="store_true")
    parser.add_argument("--prev-whitelist")
    parser.add_argument("--out-report")
    parser.add_argument("--env", default="india_prod")

    args = parser.parse_args()

    success = validate(
        args.markets,
        args.min_markets,
        args.max_removal_ratio,
        args.strict_volume,
        args.prev_whitelist,
        args.out_report,
        args.env,
    )

    sys.exit(0 if success else 2)
