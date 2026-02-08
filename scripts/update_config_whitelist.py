#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Update Freqtrade whitelist from markets dump.")
    parser.add_argument(
        "--markets", required=True, help="Path to markets JSON file (list of strings)"
    )
    parser.add_argument("--config", required=True, help="Path to Freqtrade config file")
    parser.add_argument(
        "--validate-only", action="store_true", help="Only validate whitelist, do not update"
    )

    args = parser.parse_args()

    markets_path = Path(args.markets)
    config_path = Path(args.config)

    if not markets_path.exists():
        print(f"ERROR: Markets file not found: {markets_path}")
        sys.exit(1)

    if not config_path.exists():
        print(f"ERROR: Config file not found: {config_path}")
        sys.exit(1)

    try:
        with markets_path.open("r") as f:
            markets = json.load(f)
            if not isinstance(markets, list):
                print("ERROR: Markets file must contain a JSON list.")
                sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"ERROR: Failed to parse markets JSON: {e}")
        sys.exit(1)

    try:
        with config_path.open("r") as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        print(f"ERROR: Failed to parse config JSON: {e}")
        sys.exit(1)

    exchange_conf = config.get("exchange", {})
    current_whitelist = exchange_conf.get("pair_whitelist", [])

    if args.validate_only:
        print(f"Validating {len(current_whitelist)} pairs against {len(markets)} active markets...")
        missing = [p for p in current_whitelist if p not in markets]

        if missing:
            print("ERROR: The following pairs are in whitelist but NOT active on Delta:")
            for m in missing:
                print(f" - {m}")
            sys.exit(1)
        print("SUCCESS: All whitelist pairs are valid.")

    else:
        # Update whitelist
        # Logic: If whitelist is empty or default, populate with all futures from markets dump.
        # Or simply overwrite with all available futures
        # (since list-markets filters by trading mode).
        # But dumping *all* futures might be too many (hundreds).
        # A safe approach: If whitelist has < 5 pairs (default/minimal),
        # populate with top 20 or all.
        # The prompt says: "whitelist must be generated from the list-markets output...
        # and written into config automatically".
        # Let's populate with all available markets from the dump, assuming the dump is already
        # filtered (e.g. by volume or just all futures).
        # The `list-markets` command in `validate_exchange.sh` filters by `--trading-mode futures`.

        new_whitelist = sorted(markets)

        # Avoid overwriting if no markets found (safety)
        if not new_whitelist:
            print("WARNING: No markets found in dump. Skipping whitelist update.")
            sys.exit(0)

        print(f"Updating whitelist with {len(new_whitelist)} pairs from Delta...")
        config["exchange"]["pair_whitelist"] = new_whitelist

        with config_path.open("w") as f:
            json.dump(config, f, indent=4)
        print(f"SUCCESS: Config updated: {config_path}")


if __name__ == "__main__":
    main()
