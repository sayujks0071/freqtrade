#!/usr/bin/env python3
import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path


def generate_report(markets_file, output_file=None):
    with Path(markets_file).open() as f:
        data = json.load(f)

    # Handle if data is wrapped in "markets" key
    if isinstance(data, dict) and "markets" in data:
        data = data["markets"]

    if not isinstance(data, list):
        print(f"Error: Expected a list of markets in {markets_file}")
        sys.exit(1)

    lines = []
    lines.append("# Symbol Mapping Report: Delta Exchange vs Freqtrade")
    lines.append(f"Date: {datetime.now(UTC).isoformat()}")
    lines.append("")
    lines.append("## Understanding Symbol Formats")
    lines.append(
        "- **Delta Exchange Contract Symbol**: The raw symbol used on Delta Exchange "
        "(e.g., `BTCUSDT`)."
    )
    lines.append(
        "- **Freqtrade/CCXT Pair Format**: The standardized format used in Freqtrade "
        "configuration and strategies (e.g., `BTC/USDT:USDT`)."
    )
    lines.append("")
    lines.append("## Symbol Mapping Table")
    lines.append("| Delta Contract Symbol | Freqtrade Pair Format |")
    lines.append("| --------------------- | --------------------- |")

    count = 0
    for market in data:
        # Try to find the Delta symbol. It might be in 'id' or 'info.symbol'
        delta_symbol = market.get("id")
        freqtrade_pair = market.get("symbol")

        # Sometimes id is not the contract symbol, check info
        if "info" in market and isinstance(market["info"], dict):
            info_symbol = market["info"].get("symbol")
            if info_symbol:
                delta_symbol = info_symbol

        if delta_symbol and freqtrade_pair:
            lines.append(f"| `{delta_symbol}` | `{freqtrade_pair}` |")
            count += 1

    report_content = "\n".join(lines)

    if output_file:
        out_path = Path(output_file)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w") as f:
            f.write(report_content)
        print(f"Report written to {output_file}")
    else:
        print(report_content)

    print(f"Mapped {count} symbols.")


def main():
    parser = argparse.ArgumentParser(
        description="Generate symbol mapping report from markets dump."
    )
    parser.add_argument("markets_file", help="Path to markets JSON dump")
    parser.add_argument("--output", help="Path to output Markdown file")
    args = parser.parse_args()

    # Generate default output filename if not provided
    if not args.output:
        ts = datetime.now(UTC).strftime("%Y%m%d")
        args.output = f"user_data/reports/symbol_mapping_{ts}.md"

    generate_report(args.markets_file, args.output)


if __name__ == "__main__":
    main()
