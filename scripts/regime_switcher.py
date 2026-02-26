#!/usr/bin/env python3
"""
Regime Switcher Script
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import ccxt
import pandas as pd
import pandas_ta as ta

# Configuration
CONFIG_FILE = Path("user_data/configs/config_production.json")
REGIME_LOG = Path("regime_log.md")
PAIR = "BTC/USDT"
TIMEFRAME = "1d"
LIMIT = 400


def get_market_data():
    """Fetch BTC/USDT daily candles from Kraken."""
    try:
        exchange = ccxt.kraken()

        # Load markets to check available symbols
        exchange.load_markets()
        symbol = 'BTC/USDT'
        if symbol not in exchange.markets:
            if 'XBT/USDT' in exchange.markets:
                symbol = 'XBT/USDT'
            elif 'BTC/USD' in exchange.markets:
                symbol = 'BTC/USD'

        print(f"Fetching {TIMEFRAME} data for {symbol} from Kraken...")
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=LIMIT)

        if not ohlcv:
            print("Error: No data returned.")
            return None

        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        print(f"Error fetching data: {e}")
        return None


def calculate_metrics(df):
    """Calculate EMA200, ADX(14), ATR(14)."""
    # EMA 200
    df['ema200'] = ta.ema(df['close'], length=200)

    # ADX 14
    # pandas-ta returns a DataFrame with ADX_14, DMP_14, DMN_14
    adx_df = ta.adx(df['high'], df['low'], df['close'], length=14)
    if adx_df is not None:
        df = pd.concat([df, adx_df], axis=1)

    # ATR 14
    df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14)

    return df


def detect_regime(row):
    """
    Determine market regime based on indicators.
    Returns: (regime_name, strategy_name)
    """
    price = row['close']
    ema200 = row['ema200']
    # Use standard ADX column name from pandas-ta default
    adx = row.get('ADX_14', 0)

    if pd.isna(ema200):
        return "Insufficient Data", "DeltaSafeStrategy"

    # 1. Bull Market: Price > EMA200 AND ADX > 25
    if price > ema200 and adx > 25:
        return "Bull Market", "MomentumVolumeTrend"

    # 2. Sideways/Choppy: ADX < 20 (Weak trend)
    elif adx < 20:
        return "Sideways/Choppy", "BollingerRSI"

    # 3. Volatile/Crashing: Price < EMA200 (Bearish)
    elif price < ema200:
        return "Volatile/Bearish", "VolatilityBreakout"

    # Default Fallback
    else:
        return "Transition/Uncertain", "VolatilityBreakout"


def update_config(strategy_name):
    """Update strategy in config_production.json."""
    if not CONFIG_FILE.exists():
        print(f"Config file {CONFIG_FILE} not found.")
        return False

    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)

        current_strategy = config.get("strategy")
        if current_strategy != strategy_name:
            print(f"Switching Strategy: {current_strategy} -> {strategy_name}")
            config["strategy"] = strategy_name
            with open(CONFIG_FILE, 'w') as f:
                json.dump(config, f, indent=4)
            return True
        else:
            print(f"Strategy remains: {strategy_name}")
            return False

    except Exception as e:
        print(f"Failed to update config: {e}")
        return False


def log_regime(regime, strategy, row):
    """Log decision to regime_log.md."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    price = row['close']
    ema200 = row['ema200']
    adx = row.get('ADX_14', 0)

    log_entry = f"""
## {timestamp}
- **Regime:** {regime}
- **Strategy Activated:** `{strategy}`
- **Metrics:**
  - Price: {price:.2f}
  - EMA200: {ema200:.2f}
  - ADX: {adx:.2f}
"""
    try:
        with open(REGIME_LOG, 'a') as f:
            f.write(log_entry)
        print(f"Logged to {REGIME_LOG}")
    except Exception as e:
        print(f"Failed to write log: {e}")


def main():
    parser = argparse.ArgumentParser(description="Regime Switcher")
    parser.add_argument("--dry-run", action="store_true", help="Do not update config")
    args = parser.parse_args()

    print("--- Starting Regime Detection ---")
    df = get_market_data()
    if df is None:
        return

    df = calculate_metrics(df)

    if len(df) < 201:
        print("Not enough data for indicators (need >200 candles).")
        return

    # Use the last completed candle (iloc[-2])
    target_row = df.iloc[-2]

    regime, strategy = detect_regime(target_row)

    print(f"Analysis Date: {target_row['timestamp']}")
    print(f"Regime: {regime}")
    print(f"Recommended Strategy: {strategy}")

    if not args.dry_run:
        update_config(strategy)
        log_regime(regime, strategy, target_row)
    else:
        print("[Dry Run] Config not updated.")


if __name__ == "__main__":
    main()
