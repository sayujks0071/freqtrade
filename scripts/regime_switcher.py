#!/usr/bin/env python3
import json
import sys
from datetime import datetime
from pathlib import Path

import ccxt
import pandas as pd
import pandas_ta as ta


# Path setup
ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT_DIR / "user_data/configs/config_production.json"
LOG_PATH = ROOT_DIR / "regime_log.md"


def get_market_data():
    exchange = ccxt.gateio()
    # Fetch enough candles for EMA200
    ohlcv = exchange.fetch_ohlcv("BTC/USDT", timeframe="1d", limit=300)
    df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df


def analyze_regime(df):
    df["ema200"] = ta.ema(df["close"], length=200)
    # ADX returns a DataFrame with ADX_14, DMP_14, DMN_14
    adx_df = ta.adx(df["high"], df["low"], df["close"], length=14)
    df["adx"] = adx_df["ADX_14"]

    last_row = df.iloc[-1]
    close = last_row["close"]
    ema200 = last_row["ema200"] if pd.notna(last_row["ema200"]) else 0
    adx = last_row["adx"] if pd.notna(last_row["adx"]) else 0

    # Logic
    # Bull Market: Price > EMA200, ADX > 25
    # Sideways/Choppy: ADX < 20
    # Volatile/Crashing: Price < EMA200

    regime = "Unknown"
    strategy = "MomentumVolumeTrend"  # Default

    if close > ema200 and adx > 25:
        regime = "Bull"
        strategy = "MomentumVolumeTrend"
    elif adx < 20:
        regime = "Sideways"
        strategy = "BollingerRSI"
    elif close < ema200:
        regime = "Bear/Volatile"
        strategy = "VolatilityBreakout"
    else:
        # Fallback
        if close > ema200:
            regime = "Bull (Weak Trend)"
            strategy = "MomentumVolumeTrend"
        else:
            regime = "Bear (Weak Trend)"
            strategy = "VolatilityBreakout"

    return regime, strategy, close, ema200, adx


def update_config(strategy):
    if not CONFIG_PATH.exists():
        print(f"Config file not found: {CONFIG_PATH}")
        return False

    with CONFIG_PATH.open() as f:
        config = json.load(f)

    current_strategy = config.get("strategy")
    if current_strategy == strategy:
        print(f"Strategy already set to {strategy}. No change needed.")
        return False

    config["strategy"] = strategy

    with CONFIG_PATH.open("w") as f:
        json.dump(config, f, indent=4)
    print(f"Updated config with strategy: {strategy}")
    return True


def log_decision(regime, strategy, close, ema200, adx):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    message = (
        f"| {timestamp} | {regime} | {strategy} | "
        f"Price: {close:.2f}, EMA200: {ema200:.2f}, ADX: {adx:.2f} |\n"
    )

    if not LOG_PATH.exists():
        with LOG_PATH.open("w") as f:
            f.write("| Timestamp | Regime | Strategy | Indicators |\n")
            f.write("|---|---|---|---|\n")

    with LOG_PATH.open("a") as f:
        f.write(message)
    print(f"Logged decision: {regime} -> {strategy}")


def main():
    try:
        print("Fetching market data...")
        df = get_market_data()

        print("Analyzing regime...")
        regime, strategy, close, ema200, adx = analyze_regime(df)

        print(f"Detected Regime: {regime}")
        print(f"Selected Strategy: {strategy}")

        update_config(strategy)
        log_decision(regime, strategy, close, ema200, adx)

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
