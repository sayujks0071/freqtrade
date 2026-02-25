import json
import sys
from pathlib import Path


def load_json_file(filepath):
    try:
        with Path(filepath).open() as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading file {filepath}: {e}")
        sys.exit(1)


def get_available_pairs(markets_data):
    # freqtrade list-markets --print-json returns a list of dictionaries in recent versions
    # or a dict of markets in others. We handle both.
    available_pairs = set()
    if isinstance(markets_data, dict):
        # If it's a dict, keys are likely symbols
        available_pairs = set(markets_data.keys())
        # Or if it mimics ccxt structure:
        if markets_data:
            first_market = next(iter(markets_data.values()))
            if "symbol" not in first_market:
                # It might be symbol -> details, assume keys are symbols
                pass
    elif isinstance(markets_data, list):
        for m in markets_data:
            if "symbol" in m:
                available_pairs.add(m["symbol"])
    return available_pairs


def verify_whitelist(markets_file, config_file):
    print(f"Loading markets from {markets_file}...")
    markets_data = load_json_file(markets_file)
    available_pairs = get_available_pairs(markets_data)
    print(f"Found {len(available_pairs)} available markets.")

    print(f"Loading config from {config_file}...")
    config_data = load_json_file(config_file)

    exchange_conf = config_data.get("exchange", {})
    whitelist = exchange_conf.get("pair_whitelist", [])

    print(f"Verifying {len(whitelist)} pairs from whitelist...")

    missing = []
    for pair in whitelist:
        if pair not in available_pairs:
            missing.append(pair)

    if missing:
        print("ERROR: The following pairs are in the whitelist but NOT found in the markets:")
        for m in missing:
            print(f" - {m}")
        print("Please check your whitelist or the market data.")
        sys.exit(1)

    print("All whitelist pairs are valid.")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python verify_whitelist.py <markets_file> <config_file>")
        sys.exit(1)

    verify_whitelist(sys.argv[1], sys.argv[2])
