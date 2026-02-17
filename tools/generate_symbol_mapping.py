#!/usr/bin/env python3
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def generate_mapping_report(markets_file):
    with Path(markets_file).open() as f:
        data = json.load(f)

    if isinstance(data, dict) and "markets" in data:
        data = data["markets"]

    if not isinstance(data, list):
        print("Error: Input must be a list of markets or a dict with 'markets' key.")
        sys.exit(1)

    # Header
    print(f"# Symbol Mapping Report")
    print(f"Date: {datetime.now(timezone.utc).isoformat()}")
    print(f"Source: {markets_file}")
    print("")
    print("This report maps Freqtrade pairs (standardized format) to Delta Exchange contract symbols.")
    print("Always use the Freqtrade pair format in your configuration and strategies.")
    print("")
    print("| Freqtrade Pair | Delta Symbol | Base | Quote | Settle | Active |")
    print("|---|---|---|---|---|---|")

    for m in data:
        symbol = m.get("symbol", "N/A")
        base = m.get("base", "N/A")
        quote = m.get("quote", "N/A")
        settle = m.get("settle", "N/A")
        active = m.get("active", False)

        # Delta specific info extraction
        # Freqtrade often stores the raw exchange info in 'info'
        info = m.get("info", {})
        delta_symbol = info.get("symbol", "N/A") if isinstance(info, dict) else "N/A"

        # If delta_symbol is N/A, try to infer or check if it's already in symbol
        # For Delta, Freqtrade usually maps BTC/USDT:USDT -> BTCUSDT
        if delta_symbol == "N/A":
             # Fallback: simple inference if not present
             if "/" in symbol and ":" in symbol:
                 # Likely a futures pair
                 parts = symbol.split("/")
                 coin = parts[0]
                 rest = parts[1].split(":")
                 quote_currency = rest[0]
                 # construct something like BTCUSDT
                 # But verify with actual data if possible.
                 # For now, we list what we have.
                 pass

        print(f"| `{symbol}` | `{delta_symbol}` | {base} | {quote} | {settle} | {active} |")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: generate_symbol_mapping.py <markets_json>")
        sys.exit(1)

    generate_mapping_report(sys.argv[1])
