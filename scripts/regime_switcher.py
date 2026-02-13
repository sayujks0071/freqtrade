#!/usr/bin/env python3
"""
Regime Switcher Script
Analyzes the market (BTC/USDT) and switches the strategy in config_production.json
based on the detected regime.
"""

import json
from datetime import datetime
from pathlib import Path

import ccxt
import pandas as pd
import pandas_ta as ta


# Configuration
CONFIG_PATH = Path("user_data/configs/config_production.json")
LOG_PATH = Path("user_data/regime_log.md")
PAIR = "BTC/USDT"
TIMEFRAME = "1d"
LIMIT = 300
EXCHANGE_ID = "gateio"


def fetch_ohlcv(pair: str, timeframe: str, limit: int) -> pd.DataFrame:
    """Fetches OHLCV data from the exchange."""
    exchange = getattr(ccxt, EXCHANGE_ID)()
    ohlcv = exchange.fetch_ohlcv(pair, timeframe, limit=limit)
    df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Calculates EMA200 and ADX14."""
    # EMA 200
    df["ema200"] = ta.ema(df["close"], length=200)
    # ADX 14
    adx = ta.adx(df["high"], df["low"], df["close"], length=14)
    df = pd.concat([df, adx], axis=1)
    return df


def determine_regime(df: pd.DataFrame) -> tuple[str, str]:
    """
    Determines the market regime and selects the appropriate strategy.

    Regimes:
    - Bull Market: Price > EMA200, ADX > 25 -> MomentumVolumeTrend
    - Sideways/Choppy: ADX < 20 -> BollingerRSI
    - Volatile/Crashing: Price < EMA200 -> VolatilityBreakout
    """
    last_row = df.iloc[-1]
    close_price = last_row["close"]
    ema200 = last_row["ema200"]
    # pandas_ta ADX column name is usually ADX_14
    adx = last_row["ADX_14"]

    # Logic priority
    if close_price < ema200:
        return "VolatilityBreakout", f"Bear/Crash (Price {close_price:.2f} < EMA200 {ema200:.2f})"
    elif adx < 20:
        return "BollingerRSI", f"Sideways/Choppy (ADX {adx:.2f} < 20)"
    elif close_price > ema200 and adx > 25:
        msg = f"Bull Market (Price {close_price:.2f} > EMA200 {ema200:.2f}, ADX {adx:.2f} > 25)"
        return "MomentumVolumeTrend", msg
    else:
        # Default or ambiguous state
        msg = f"Default/Ambiguous (Price {close_price:.2f}, EMA200 {ema200:.2f}, ADX {adx:.2f})"
        return "MomentumVolumeTrend", msg


def update_config(strategy_name: str):
    """Updates the strategy in the configuration file."""
    if not CONFIG_PATH.exists():
        print(f"Error: Config file not found at {CONFIG_PATH}")
        return

    # Use a simpler load because we want to preserve structure if possible,
    # but json dump will reformat it. Freqtrade config is standard JSON.
    try:
        with CONFIG_PATH.open("r") as f:
            config = json.load(f)

        current_strategy = config.get("strategy")
        if current_strategy == strategy_name:
            print(f"Strategy is already {strategy_name}. No change needed.")
            return

        config["strategy"] = strategy_name

        with CONFIG_PATH.open("w") as f:
            json.dump(config, f, indent=4)

        print(f"Updated config with strategy: {strategy_name}")

    except Exception as e:
        print(f"Failed to update config: {e}")


def log_decision(strategy_name: str, reason: str):
    """Logs the decision to the log file."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"| {timestamp} | {strategy_name} | {reason} |\n"

    # Create header if file doesn't exist
    if not LOG_PATH.exists():
        with LOG_PATH.open("w") as f:
            f.write("| Timestamp | Strategy | Reason |\n")
            f.write("|---|---|---|\n")

    with LOG_PATH.open("a") as f:
        f.write(log_entry)
    print(f"Logged decision: {strategy_name} - {reason}")


def main():
    print("Starting Regime Switcher...")
    try:
        df = fetch_ohlcv(PAIR, TIMEFRAME, LIMIT)
        df = calculate_indicators(df)
        strategy, reason = determine_regime(df)

        print(f"Detected Regime: {strategy} because {reason}")

        update_config(strategy)
        log_decision(strategy, reason)

        print("Regime Switcher completed successfully.")

    except Exception as e:
        print(f"An error occurred: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
