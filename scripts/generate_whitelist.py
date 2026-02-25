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


def save_json_file(filepath, data):
    try:
        with Path(filepath).open("w") as f:
            json.dump(data, f, indent=4)
        print("Config updated successfully.")
    except Exception as e:
        print(f"Error updating file {filepath}: {e}")
        sys.exit(1)


def extract_valid_pairs(markets_data):
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
    if not valid_pairs:
        print("No valid pairs found.")
        sys.exit(1)

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

    # If priority pairs not found (different naming convention?), take first 5
    if not selected_pairs:
        print("Priority pairs not found. Selecting top 5 available pairs.")
        selected_pairs = valid_pairs[:5]

    return selected_pairs


def generate_whitelist(markets_file, config_file):
    print(f"Loading markets from {markets_file}...")
    markets_data = load_json_file(markets_file)
    valid_pairs = extract_valid_pairs(markets_data)
    print(f"Found {len(valid_pairs)} active pairs.")

    selected_pairs = select_pairs(valid_pairs)
    print(f"Selected whitelist: {selected_pairs}")

    print(f"Updating config {config_file}...")
    config_data = load_json_file(config_file)

    # Ensure structure exists
    if "exchange" not in config_data:
        config_data["exchange"] = {}

    config_data["exchange"]["pair_whitelist"] = selected_pairs
    save_json_file(config_file, config_data)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python generate_whitelist.py <markets_file> <config_file>")
        sys.exit(1)

    generate_whitelist(sys.argv[1], sys.argv[2])
