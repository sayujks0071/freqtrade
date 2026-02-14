#!/usr/bin/env python3
import json
import requests
from datetime import datetime, UTC
from pathlib import Path


def fetch_markets():
    url = "https://api.delta.exchange/v2/products"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Failed to fetch markets: {e}")
        return None


def generate_report():
    data = fetch_markets()
    if not data:
        return

    markets = data.get("result", [])

    perpetuals = [m for m in markets if m.get("contract_type") == "perpetual_futures"]

    # Sort by symbol
    perpetuals.sort(key=lambda x: x["symbol"])

    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    report_file = Path(f"user_data/reports/symbol_mapping_{timestamp}.md")
    report_file.parent.mkdir(parents=True, exist_ok=True)

    content = f"""# Delta Exchange Symbol Mapping Report
Date: {datetime.now(UTC).isoformat()}

## Overview
This report documents the mapping between Delta Exchange contract symbols
and Freqtrade Futures pair formats.

### Format Definition
- **Delta Symbol**: The raw symbol used by Delta Exchange API (e.g., `BTCUSDT`).
- **Freqtrade Pair**: The standardized format used in Freqtrade configuration and strategies
  (e.g., `BTC/USDT:USDT`).

**Formula:** `BASE/QUOTE:SETTLE`

## Examples (Perpetual Futures)

| Delta Symbol | Base Asset | Quote Asset | Settle Asset | Freqtrade Pair |
| :--- | :--- | :--- | :--- | :--- |
"""

    # Limit to first 50 to avoid massive files in repo if checked in,
    # but practically we want them all available.
    # For this task, I'll generate a comprehensive list but maybe truncate
    # for the PR description if needed.

    for m in perpetuals:
        symbol = m["symbol"]
        base = m["underlying_asset"]["symbol"]
        quote = m["quoting_asset"]["symbol"]
        settle = m["settling_asset"]["symbol"]

        freqtrade_pair = f"{base}/{quote}:{settle}"

        content += f"| `{symbol}` | {base} | {quote} | {settle} | `{freqtrade_pair}` |\n"

    content += """
## How to use
1. Copy the **Freqtrade Pair** string.
2. Paste it into your `whitelist` in `config.json` or `whitelist.delta.json`.
3. Ensure your strategy's `symbol_sanity_check` validates this format.

## Notes
- Only perpetual futures are shown above.
- Options symbols require different handling.
"""

    with report_file.open("w", encoding="utf-8") as f:
        f.write(content)

    print(f"Report generated: {report_file}")


if __name__ == "__main__":
    generate_report()
