import json
import sys


def generate_whitelist(markets_file, config_file):
    print(f"Loading markets from {markets_file}...")
    try:
        with open(markets_file) as f:
            markets_data = json.load(f)
    except Exception as e:
        print(f"Error loading markets file: {e}")
        sys.exit(1)

    # Convert to list of dicts if needed
    markets = []
    if isinstance(markets_data, dict):
        markets = list(markets_data.values())
    elif isinstance(markets_data, list):
        markets = markets_data

    # Filter for active futures
    # Delta futures usually have 'linear' in type or info.
    # Or just rely on what freqtrade list-markets returned (if it was called with --trading-mode futures, it should be futures)

    valid_pairs = []
    for m in markets:
        # Check if active?
        if m.get("active") is False:
            continue
        if "symbol" in m:
            valid_pairs.append(m["symbol"])

    print(f"Found {len(valid_pairs)} active pairs.")

    if not valid_pairs:
        print("No valid pairs found.")
        sys.exit(1)

    # Strategy for selection:
    # 1. Look for BTC and ETH first (standard base pairs)
    # 2. Then others.

    selected_pairs = []

    # Priority list
    priority = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "XRP/USDT:USDT", "BNB/USDT:USDT"]

    for p in priority:
        if p in valid_pairs:
            selected_pairs.append(p)

    # If priority pairs not found (different naming convention?), take first 5
    if not selected_pairs:
        print("Priority pairs not found. Selecting top 5 available pairs.")
        selected_pairs = valid_pairs[:5]

    print(f"Selected whitelist: {selected_pairs}")

    print(f"Updating config {config_file}...")
    try:
        with open(config_file) as f:
            config_data = json.load(f)

        # Ensure structure exists
        if "exchange" not in config_data:
            config_data["exchange"] = {}

        config_data["exchange"]["pair_whitelist"] = selected_pairs

        with open(config_file, "w") as f:
            json.dump(config_data, f, indent=4)

        print("Config updated successfully.")
    except Exception as e:
        print(f"Error updating config file: {e}")
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python generate_whitelist.py <markets_file> <config_file>")
        sys.exit(1)

    generate_whitelist(sys.argv[1], sys.argv[2])
