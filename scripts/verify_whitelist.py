import sys
import json

def verify_whitelist(markets_file, config_file):
    print(f"Loading markets from {markets_file}...")
    try:
        with open(markets_file, 'r') as f:
            markets_data = json.load(f)
    except Exception as e:
        print(f"Error loading markets file: {e}")
        sys.exit(1)

    # freqtrade list-markets --print-json returns a list of dictionaries in recent versions
    # or a dict of markets in others. We handle both.
    available_pairs = set()
    if isinstance(markets_data, dict):
        # If it's a dict, keys are likely symbols
        available_pairs = set(markets_data.keys())
        # Or if it mimics ccxt structure:
        if 'symbol' not in list(markets_data.values())[0]:
             # It might be symbol -> details
             pass
    elif isinstance(markets_data, list):
        for m in markets_data:
            if 'symbol' in m:
                available_pairs.add(m['symbol'])

    print(f"Found {len(available_pairs)} available markets.")

    print(f"Loading config from {config_file}...")
    try:
        with open(config_file, 'r') as f:
            config_data = json.load(f)
    except Exception as e:
        print(f"Error loading config file: {e}")
        sys.exit(1)

    exchange_conf = config_data.get('exchange', {})
    whitelist = exchange_conf.get('pair_whitelist', [])

    print(f"Verifying {len(whitelist)} pairs from whitelist...")

    missing = []
    for pair in whitelist:
        if pair not in available_pairs:
            missing.append(pair)

    if missing:
        print(f"ERROR: The following pairs are in the whitelist but NOT found in the markets:")
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
