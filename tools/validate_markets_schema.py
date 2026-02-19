"""
Market Schema Validator
Validates market data dump from Freqtrade/CCXT against strict schema and drift rules.
Exits with 0 if PASS, 2 if FAIL.
"""

import argparse
import json
import logging
import re
import sys
from datetime import UTC, datetime
from pathlib import Path


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Constants
REQUIRED_FIELDS = ["symbol", "base", "quote", "active", "contract"]
FUTURES_REGEX = re.compile(r"^[A-Z0-9]+/[A-Z0-9]+:[A-Z0-9]+$")  # e.g., BTC/USDT:USDT


def parse_args():
    parser = argparse.ArgumentParser(description="Validate Market Schema")
    parser.add_argument("markets_file", type=Path, help="Current markets JSON dump")
    parser.add_argument(
        "--prev-dump", type=Path, help="Previous markets JSON dump for drift check", default=None
    )
    parser.add_argument("--min-markets", type=int, default=20, help="Minimum active markets")
    parser.add_argument("--max-removal-ratio", type=float, default=0.25, help="Max removal ratio")
    parser.add_argument("--strict-volume", action="store_true", help="Fail on low volume")
    parser.add_argument(
        "--report-dir", type=Path, default=Path("user_data/reports"), help="Report directory"
    )
    return parser.parse_args()


def load_market_data(filepath: Path) -> list[dict]:
    try:
        with filepath.open("r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, list):
                logger.error(f"File {filepath} content is not a list.")
                sys.exit(2)
            return data
    except Exception as e:
        logger.error(f"Failed to load {filepath}: {e}")
        sys.exit(2)


def validate_schema(market: dict) -> list[str]:
    errors = []
    # Check required fields
    for field in REQUIRED_FIELDS:
        if field not in market:
            errors.append(f"Missing field: {field}")

    if errors:
        return errors

    # Check symbol format (Futures)
    if market.get("contract"):
        if not FUTURES_REGEX.match(market["symbol"]):
            errors.append(f"Invalid futures symbol format: {market['symbol']}")

    # Check active status type
    if not isinstance(market.get("active"), bool):
        errors.append(f"Field 'active' must be boolean: {market.get('active')}")

    return errors


def check_drift(current_markets, prev_dump_path, max_removal_ratio):
    drift_report = []
    if prev_dump_path and prev_dump_path.exists():
        logger.info(f"Checking drift against {prev_dump_path}...")
        prev_markets = load_market_data(prev_dump_path)
        prev_symbols = {m["symbol"] for m in prev_markets if m.get("active")}
        curr_symbols = {m["symbol"] for m in current_markets if m.get("active")}

        removed = prev_symbols - curr_symbols
        added = curr_symbols - prev_symbols

        removal_ratio = len(removed) / len(prev_symbols) if len(prev_symbols) > 0 else 0.0

        drift_report.append(f"Previous Active: {len(prev_symbols)}")
        drift_report.append(f"Current Active: {len(curr_symbols)}")
        drift_report.append(f"Removed: {len(removed)} ({removal_ratio:.2%})")
        drift_report.append(f"Added: {len(added)}")

        if removal_ratio > max_removal_ratio:
            logger.error(f"Removal ratio {removal_ratio:.2%} > limit {max_removal_ratio:.2%}")
            logger.error(f"Removed pairs: {', '.join(list(removed)[:10])}...")
            sys.exit(2)
    else:
        drift_report.append("No previous dump found. Skipping drift check.")
    return drift_report


def write_report(report_dir, markets_file, active_count, drift_report):
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    report_file = report_dir / f"markets_schema_report_{timestamp}.md"
    with report_file.open("w") as f:
        f.write("# Market Schema Validation Report\n\n")
        f.write(f"Date: {datetime.now(UTC).isoformat()}\n")
        f.write(f"File: {markets_file}\n")
        f.write(f"Active Markets: {active_count}\n\n")
        f.write("## Schema Checks\n")
        f.write("- JSON Parse: PASS\n")
        f.write("- Required Fields: PASS\n")
        f.write("- Symbol Format: PASS\n")
        f.write("- Uniqueness: PASS\n\n")
        f.write("## Drift Report\n")
        for line in drift_report:
            f.write(f"- {line}\n")
    logger.info("Validation Passed.")


def main():
    args = parse_args()

    logger.info(f"Validating {args.markets_file}...")

    current_markets = load_market_data(args.markets_file)

    # 1. Basic Count Check
    active_markets = [m for m in current_markets if m.get("active")]
    if len(active_markets) < args.min_markets:
        logger.error(f"Too few active markets: {len(active_markets)} < {args.min_markets}")
        sys.exit(2)

    # 2. Schema Validation
    schema_errors = []
    symbols = set()
    for m in current_markets:
        if not m.get("active"):
            continue

        errs = validate_schema(m)
        if errs:
            schema_errors.extend([f"{m.get('symbol', 'UNKNOWN')}: {e}" for e in errs])

        # Uniqueness
        sym = m.get("symbol")
        if sym:
            if sym.upper() in symbols:
                schema_errors.append(f"Duplicate symbol: {sym}")
            symbols.add(sym.upper())

    if schema_errors:
        logger.error(f"Schema Validation Failed ({len(schema_errors)} errors):")
        for e in schema_errors[:10]:
            logger.error(f" - {e}")
        if len(schema_errors) > 10:
            logger.error("... and more.")
        sys.exit(2)

    # 3. Drift Check
    drift_report = check_drift(current_markets, args.prev_dump, args.max_removal_ratio)

    # 4. Generate Report
    write_report(args.report_dir, args.markets_file, len(active_markets), drift_report)

    sys.exit(0)


if __name__ == "__main__":
    main()
