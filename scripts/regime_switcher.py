#!/usr/bin/env python3
"""
Regime Switcher Script
Analyzes market conditions and updates the production config with the appropriate strategy.
"""

import ccxt
import pandas as pd
import pandas_ta as ta
import json
from pathlib import Path
from datetime import datetime, timezone
import traceback

# Configuration
SYMBOL = "BTC/USDT"
TIMEFRAME = "1d"
LIMIT = 300  # Enough for EMA200
CONFIG_PATH = Path("user_data/configs/config_production.json")
LOG_PATH = Path("regime_log.md")

# Strategies
STRATEGY_BULL = "MomentumVolumeTrend"
STRATEGY_SIDEWAYS = "BollingerRSI"
STRATEGY_BEAR = "VolatilityBreakout"


def fetch_data(symbol, timeframe, limit):
    print(f"Fetching data for {symbol} ({timeframe})...")
    # Use Gate.io as it is the primary exchange and might be accessible
    exchange = ccxt.gateio()

    ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
    df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df


def calculate_indicators(df):
    df.ta.ema(length=200, append=True)
    df.ta.adx(length=14, append=True)
    return df


def detect_regime(df):
    current = df.iloc[-1]
    close = current["close"]

    # pandas_ta column names might vary slightly, typically EMA_200 and ADX_14
    # We check columns to be safe or assume standard naming
    ema_col = "EMA_200"
    adx_col = "ADX_14"

    if ema_col not in df.columns:
        print(f"Columns found: {df.columns}")
        raise ValueError(f"{ema_col} not found in dataframe")

    ema200 = current[ema_col]
    adx = current[adx_col]

    print(f"Current State: Price={close:.2f}, EMA200={ema200:.2f}, ADX={adx:.2f}")

    # Logic:
    # 1. Bear check: Price < EMA200 -> Bear
    if close < ema200:
        return "Volatile/Bear", STRATEGY_BEAR

    # 2. Bull check: Price > EMA200 & ADX > 25
    if close > ema200 and adx > 25:
        return "Bull Market", STRATEGY_BULL

    # 3. Sideways check: ADX < 20 (and Price > EMA200 since we passed check 1)
    if adx < 20:
        return "Sideways/Choppy", STRATEGY_SIDEWAYS

    # 4. Neutral/Transition
    return "Neutral/Transition", STRATEGY_SIDEWAYS


def update_config(strategy_name):
    if not CONFIG_PATH.exists():
        print(f"Error: Config file not found at {CONFIG_PATH}")
        return False

    try:
        with open(CONFIG_PATH, "r") as f:
            config = json.load(f)

        current_strategy = config.get("strategy")
        if current_strategy == strategy_name:
            print(f"Config already set to {strategy_name}. No change needed.")
            return False

        config["strategy"] = strategy_name

        with open(CONFIG_PATH, "w") as f:
            json.dump(config, f, indent=4)
        print(f"Updated config to use {strategy_name}")
        return True
    except Exception as e:
        print(f"Failed to update config: {e}")
        return False


def log_regime(regime, strategy, changed):
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    action = "Switched to" if changed else "Maintained"
    message = f"| {timestamp} | {regime} | {action} {strategy} |"

    print(message)

    if not LOG_PATH.exists():
        with open(LOG_PATH, "w") as f:
            f.write("| Timestamp | Regime | Action |\n")
            f.write("|---|---|---|\n")

    with open(LOG_PATH, "a") as f:
        f.write(message + "\n")


def main():
    try:
        df = fetch_data(SYMBOL, TIMEFRAME, LIMIT)
        df = calculate_indicators(df)
        regime, strategy = detect_regime(df)

        changed = update_config(strategy)
        log_regime(regime, strategy, changed)

    except Exception as e:
        print(f"An error occurred: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    main()
