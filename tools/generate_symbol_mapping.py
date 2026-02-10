import json
from datetime import datetime
from pathlib import Path


MARKETS_FILE = "tests/testdata/delta_markets_mock.json"
REPORT_FILE = f"user_data/reports/symbol_mapping_{datetime.now().strftime('%Y%m%d')}.md"


def main():
    if not Path(MARKETS_FILE).exists():
        print(f"Markets file {MARKETS_FILE} not found.")
        return

    with Path(MARKETS_FILE).open() as f:
        markets = json.load(f)

    # If it's a dict with "markets" key
    if isinstance(markets, dict) and "markets" in markets:
        markets = markets["markets"]

    report = f"""# Delta Exchange Symbol Mapping
Date: {datetime.now().isoformat()}

This report maps Delta Exchange contract symbols to Freqtrade futures pair format.

| Delta Symbol | Freqtrade Pair | Type |
|---|---|---|
"""

    for m in markets:
        ft_symbol = m.get("symbol")
        delta_info = m.get("info", {})
        delta_symbol = delta_info.get("symbol", "N/A")
        contract_type = delta_info.get("contract_type", "N/A")

        report += f"| {delta_symbol} | {ft_symbol} | {contract_type} |\n"

    report += "\n\n## Instructions\n"
    report += "- Use 'Freqtrade Pair' in your `whitelist.delta.json`.\n"
    report += "- Use 'Delta Symbol' when searching on Delta Exchange website.\n"

    with Path(REPORT_FILE).open("w") as f:
        f.write(report)

    print(f"Report written to {REPORT_FILE}")


if __name__ == "__main__":
    main()
