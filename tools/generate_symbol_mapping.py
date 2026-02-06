#!/usr/bin/env python3
import glob
import json
import os
from datetime import datetime, timezone
from pathlib import Path


def generate_mapping_report():
    reports_dir = Path("user_data/reports")
    # Find latest markets_*.json
    market_files = sorted(reports_dir.glob("markets_*.json"), key=os.path.getmtime, reverse=True)

    if not market_files:
        print("No market dump found in user_data/reports/")
        return

    latest_file = market_files[0]
    print(f"Reading markets from {latest_file}")

    with latest_file.open("r") as f:
        try:
            markets = json.load(f)
        except json.JSONDecodeError:
            print("Failed to decode JSON.")
            return

    # Filter for futures usually (has :)
    futures = [m for m in markets if ":" in m]

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    output_file = reports_dir / f"symbol_mapping_{timestamp}.md"

    content = f"""# Delta Exchange Symbol Mapping ({timestamp})

This report maps Delta Exchange contract symbols to Freqtrade/CCXT futures pair format.

## Format Explanation

- **Delta Exchange Contract**: The symbol used on Delta Exchange website (e.g., `BTCUSDT`).
- **Freqtrade/CCXT Pair**: The standardized format used in configuration (e.g., `BTC/USDT:USDT`).

Format: `BASE/QUOTE:SETTLE`

## Examples from Market Dump

Total Markets Found: {len(markets)}
Futures/Swaps Found: {len(futures)}

| Freqtrade Pair | inferred Base | Quote | Settle |
| :--- | :--- | :--- | :--- |
"""

    # Add top 20 examples
    for pair in futures[:20]:
        # Parse pair BTC/USDT:USDT
        try:
            base, rest = pair.split("/")
            quote, settle = rest.split(":")
            content += f"| `{pair}` | {base} | {quote} | {settle} |\n"
        except ValueError:
            content += f"| `{pair}` | ? | ? | ? |\n"

    content += """
## How to use

1. Copy the **Freqtrade Pair** string.
2. Paste it into your `whitelist.delta.json` or `config.delta.dryrun.json`.
"""

    with output_file.open("w") as f:
        f.write(content)

    print(f"Generated report: {output_file}")


if __name__ == "__main__":
    generate_mapping_report()
