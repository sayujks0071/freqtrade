#!/usr/bin/env python3
import json
from datetime import datetime, timezone
from pathlib import Path


def main():
    report_dir = Path("user_data/reports")
    report_dir.mkdir(parents=True, exist_ok=True)

    # Find latest markets dump
    dumps = list(report_dir.glob("markets_*.json"))
    dumps.sort(reverse=True)

    pairs = []
    source = "Static Examples (No markets dump found)"

    if dumps:
        latest_dump = dumps[0]
        source = str(latest_dump)
        try:
            with latest_dump.open() as f:
                data = json.load(f)
                if isinstance(data, dict) and "markets" in data:
                    data = data["markets"]

                # Extract pairs that look like futures
                for m in data:
                    symbol = m.get("symbol", "")
                    # Check for :SETTLE or just assume all are from dump
                    if ":" in symbol:
                        pairs.append(symbol)
        except Exception as e:
            print(f"Error reading dump {latest_dump}: {e}")

    if not pairs:
        # Default examples
        pairs = [
            "BTC/USDT:USDT",
            "ETH/USDT:USDT",
            "SOL/USDT:USDT",
            "XRP/USDT:USDT",
            "DOGE/USDT:USDT",
        ]

    # Generate Report
    ts = datetime.now(timezone.utc).strftime("%Y%m%d")  # noqa: UP017
    report_file = report_dir / f"symbol_mapping_{ts}.md"

    content = f"""# Delta Exchange vs Freqtrade Symbol Mapping
Date: {datetime.now(timezone.utc).isoformat()}  # noqa: UP017
Source: {source}

## Symbology Explanation

**Delta Exchange Contract**: Typically `BTCUSDT` (Inverse) or `BTCUSDT` (Linear, often with suffix).
**Freqtrade/CCXT Pair**: `BASE/QUOTE:SETTLE`.

For Linear Futures (USDT settled):
- Base: BTC
- Quote: USDT
- Settle: USDT
- Symbol: `BTC/USDT:USDT`

For Inverse Futures (Coin settled):
- Base: BTC
- Quote: USD
- Settle: BTC
- Symbol: `BTC/USD:BTC`

## Available Pairs (Examples)

The following are examples of valid Freqtrade pair formats for Delta Exchange,
based on available market data:

"""

    for p in pairs[:50]:  # Limit to 50 examples
        content += f"- `{p}`\n"

    if len(pairs) > 50:
        content += f"\n... and {len(pairs) - 50} more."

    with report_file.open("w") as f:
        f.write(content)

    print(f"Report generated: {report_file}")


if __name__ == "__main__":
    main()
