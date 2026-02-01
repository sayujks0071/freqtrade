import json
import sys
from pathlib import Path


def load_markets(markets_file):
    print(f"Loading markets from {markets_file}...")
    try:
        with Path(markets_file).open() as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading markets file: {e}")
        sys.exit(1)


def filter_pairs(markets_data):
    # Convert to list of dicts if needed
    markets = []
    if isinstance(markets_data, dict):
        markets = list(markets_data.values())
    elif isinstance(markets_data, list):
        markets = markets_data

    valid_pairs = []
    for m in markets:
        # Check if active?
        if m.get("active") is False:
            continue
        if "symbol" in m:
            valid_pairs.append(m["symbol"])
    return valid_pairs


def select_pairs(valid_pairs):
    selected_pairs = []
    # Priority list
    priority = [
        "BTC/USDT:USDT",
        "ETH/USDT:USDT",
        "SOL/USDT:USDT",
        "XRP/USDT:USDT",
        "BNB/USDT:USDT",
    ]

    for p in priority:
        if p in valid_pairs:
            selected_pairs.append(p)

    # If priority pairs not found, take first 5
    if not selected_pairs:
        print("Priority pairs not found. Selecting top 5 available pairs.")
        selected_pairs = valid_pairs[:5]

    return selected_pairs


def update_config(config_file, selected_pairs):
    print(f"Updating config {config_file}...")
    try:
        path = Path(config_file)
        with path.open() as f:
            config_data = json.load(f)

        # Ensure structure exists
        if "exchange" not in config_data:
            config_data["exchange"] = {}

        config_data["exchange"]["pair_whitelist"] = selected_pairs

        with path.open("w") as f:
            json.dump(config_data, f, indent=4)

        print("Config updated successfully.")
    except Exception as e:
        print(f"Error updating config file: {e}")
        sys.exit(1)


def generate_whitelist(markets_file, config_file):
    markets_data = load_markets(markets_file)
    valid_pairs = filter_pairs(markets_data)

    print(f"Found {len(valid_pairs)} active pairs.")

    if not valid_pairs:
        print("No valid pairs found.")
        sys.exit(1)

    selected_pairs = select_pairs(valid_pairs)
    print(f"Selected whitelist: {selected_pairs}")

    update_config(config_file, selected_pairs)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python generate_whitelist.py <markets_file> <config_file>")
        sys.exit(1)

    generate_whitelist(sys.argv[1], sys.argv[2])
