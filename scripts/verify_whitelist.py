import json
import sys
from pathlib import Path


def load_json(filepath):
    try:
        with Path(filepath).open() as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading {filepath}: {e}")
        sys.exit(1)


def get_available_pairs(markets_data):
    available_pairs = set()
    if isinstance(markets_data, dict):
        available_pairs = set(markets_data.keys())
        # Check if first value has 'symbol', using next(iter()) to avoid list() slice
        first_value = next(iter(markets_data.values()), {})
        if isinstance(first_value, dict) and "symbol" not in first_value:
            # It might be symbol -> details
            pass
    elif isinstance(markets_data, list):
        for m in markets_data:
            if "symbol" in m:
                available_pairs.add(m["symbol"])
    return available_pairs


def check_whitelist(available_pairs, config_data):
    exchange_conf = config_data.get("exchange", {})
    whitelist = exchange_conf.get("pair_whitelist", [])

    print(f"Verifying {len(whitelist)} pairs from whitelist...")

    missing = []
    for pair in whitelist:
        if pair not in available_pairs:
            missing.append(pair)

    if missing:
        print(
            "ERROR: The following pairs are in the whitelist but "
            "NOT found in the markets:"
        )
        for m in missing:
            print(f" - {m}")
        print("Please check your whitelist or the market data.")
        sys.exit(1)

    print("All whitelist pairs are valid.")


def verify_whitelist(markets_file, config_file):
    print(f"Loading markets from {markets_file}...")
    markets_data = load_json(markets_file)
    available_pairs = get_available_pairs(markets_data)

    print(f"Found {len(available_pairs)} available markets.")

    print(f"Loading config from {config_file}...")
    config_data = load_json(config_file)

    check_whitelist(available_pairs, config_data)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python verify_whitelist.py <markets_file> <config_file>")
        sys.exit(1)

    verify_whitelist(sys.argv[1], sys.argv[2])
