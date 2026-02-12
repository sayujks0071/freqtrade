#!/usr/bin/env python3
"""
Regime Switcher Script
Analyzes BTC/USDT market data to determine the current market regime
and updates the production configuration with the appropriate strategy.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

import ccxt
import pandas as pd
import pandas_ta as ta  # noqa: F401


def fetch_data(symbol="BTC/USDT", timeframe="1d", limit=300):
    """
    Fetch OHLCV data from Gate.io
    """
    exchange = ccxt.gateio()
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        return df
    except Exception as e:
        print(f"Error fetching data: {e}")
        sys.exit(1)


def calculate_indicators(df):
    """
    Calculate EMA200 and ADX(14)
    """
    # EMA 200
    df["ema200"] = df.ta.ema(length=200)
    # ADX 14
    adx = df.ta.adx(length=14)
    # adx dataframe usually has ADX_14, DMP_14, DMN_14 columns. We want ADX_14.
    # The column name might be 'ADX_14' or 'ADX'.
    # pandas_ta returns a DataFrame for adx() call.
    df = pd.concat([df, adx], axis=1)

    # Identify ADX column
    adx_col = next(c for c in df.columns if c.startswith("ADX"))
    df["adx"] = df[adx_col]

    return df


def determine_regime(df):
    """
    Determine regime based on latest candle
    """
    last_row = df.iloc[-1]
    close = last_row["close"]
    ema200 = last_row["ema200"]
    adx = last_row["adx"]

    # Logic
    # Bull: Price > EMA200 AND ADX > 25
    # Sideways: ADX < 20
    # Volatile/Crashing: Price < EMA200 (Simplified from prompt)

    # Priority:
    # If Price < EMA200 -> Bear (VolatilityBreakout)
    # Else if ADX < 20 -> Sideways (BollingerRSI)
    # Else if Price > EMA200 and ADX > 25 -> Bull (MomentumVolumeTrend)
    # Else -> Default/Hold (maybe stick to current or fallback to Sideways/Bull depending on bias).
    # The prompt gives specific conditions. I will follow them.
    # What if none match? (e.g. Price > EMA200 but ADX is 22).
    # Prompt:
    # Bull: Price > EMA200, ADX > 25
    # Sideways: ADX < 20
    # Volatile/Crashing: Price < EMA200

    # Overlap/Gap handling:
    # Price < EMA200 triggers Bear.
    # If Price > EMA200:
    #   If ADX > 25 -> Bull.
    #   If ADX < 20 -> Sideways.
    #   If 20 <= ADX <= 25 -> Undefined. Default to Sideways (BollingerRSI).

    regime = "Unknown"
    strategy = "DeltaSafeStrategy"  # Default
    unidirectional = True

    if close < ema200:
        regime = "Volatile/Crashing"
        strategy = "VolatilityBreakout"
        unidirectional = False  # Enable shorts
    elif adx < 20:
        regime = "Sideways/Choppy"
        strategy = "BollingerRSI"
        unidirectional = True
    elif close > ema200 and adx > 25:
        regime = "Bull Market"
        strategy = "MomentumVolumeTrend"
        unidirectional = True
    else:
        # Fallback for undefined zone (Price > EMA200, 20 <= ADX <= 25)
        regime = "Transition (Bull/Sideways)"
        strategy = "BollingerRSI"  # Safer bet
        unidirectional = True

    return regime, strategy, unidirectional, close, ema200, adx


def update_config(strategy, unidirectional):
    """
    Update config_production.json
    """
    config_path = Path("user_data/configs/config_production.json")
    if not config_path.exists():
        print(f"Config file not found: {config_path}")
        return

    try:
        with config_path.open() as f:
            config = json.load(f)

        current_strategy = config.get("strategy")
        current_uni = config.get("unidirectional_only")

        if current_strategy != strategy or current_uni != unidirectional:
            print(f"Switching strategy: {current_strategy} -> {strategy}")
            config["strategy"] = strategy
            config["unidirectional_only"] = unidirectional

            with config_path.open("w") as f:
                json.dump(config, f, indent=4)
        else:
            print("No strategy change needed.")

    except Exception as e:
        print(f"Error updating config: {e}")


def log_decision(regime, strategy, close, ema200, adx):
    """
    Log to regime_log.md
    """
    log_path = Path("regime_log.md")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    log_entry = (
        f"| {timestamp} | {regime} | {strategy} | {close:.2f} | {ema200:.2f} | {adx:.2f} |\n"
    )

    if not log_path.exists():
        with log_path.open("w") as f:
            f.write("| Timestamp | Regime | Strategy | BTC Price | EMA200 | ADX |\n")
            f.write("|---|---|---|---|---|---|\n")

    with log_path.open("a") as f:
        f.write(log_entry)

    print(f"Logged: {regime} -> {strategy}")


def main():
    print("Starting Regime Switcher...")
    df = fetch_data()
    if df.empty:
        print("No data fetched.")
        return

    df = calculate_indicators(df)

    # Check if we have enough data for EMA200
    if pd.isna(df.iloc[-1]["ema200"]):
        print("Not enough data for EMA200.")
        return

    regime, strategy, unidirectional, close, ema200, adx = determine_regime(df)

    print(f"Current Regime: {regime}")
    print(f"BTC Price: {close:.2f}, EMA200: {ema200:.2f}, ADX: {adx:.2f}")

    update_config(strategy, unidirectional)
    log_decision(regime, strategy, close, ema200, adx)
    print("Done.")


if __name__ == "__main__":
    main()
