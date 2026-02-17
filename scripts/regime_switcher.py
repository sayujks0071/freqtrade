
import json
from datetime import UTC, datetime
from pathlib import Path

import ccxt
import numpy as np
import pandas as pd


def calculate_ema(series, span):
    return series.ewm(span=span, adjust=False).mean()


def calculate_adx(df, period=14):
    # True Range
    df["h-l"] = df["high"] - df["low"]
    df["h-pc"] = abs(df["high"] - df["close"].shift(1))
    df["l-pc"] = abs(df["low"] - df["close"].shift(1))
    df["tr"] = df[["h-l", "h-pc", "l-pc"]].max(axis=1)

    # Directional Movement
    df["up_move"] = df["high"] - df["high"].shift(1)
    df["down_move"] = df["low"].shift(1) - df["low"]

    df["plus_dm"] = np.where(
        (df["up_move"] > df["down_move"]) & (df["up_move"] > 0), df["up_move"], 0
    )
    df["minus_dm"] = np.where(
        (df["down_move"] > df["up_move"]) & (df["down_move"] > 0), df["down_move"], 0
    )

    # Smoothed TR and DM (Wilder's Smoothing)
    alpha = 1 / period
    df["tr_smooth"] = df["tr"].ewm(alpha=alpha, adjust=False).mean()
    df["plus_dm_smooth"] = df["plus_dm"].ewm(alpha=alpha, adjust=False).mean()
    df["minus_dm_smooth"] = df["minus_dm"].ewm(alpha=alpha, adjust=False).mean()

    df["plus_di"] = 100 * (df["plus_dm_smooth"] / df["tr_smooth"])
    df["minus_di"] = 100 * (df["minus_dm_smooth"] / df["tr_smooth"])

    df["dx"] = 100 * abs(df["plus_di"] - df["minus_di"]) / (df["plus_di"] + df["minus_di"])
    df["adx"] = df["dx"].ewm(alpha=alpha, adjust=False).mean()

    return df["adx"]


def get_market_data():
    try:
        # Use Kraken for BTC/USD data as it is reliable and has long history
        exchange = ccxt.kraken()
        # Fetch daily candles, enough for EMA200 warmup
        ohlcv = exchange.fetch_ohlcv("BTC/USD", timeframe="1d", limit=1000)
        df = pd.DataFrame(
            ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"]
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        return df
    except Exception as e:
        print(f"Error fetching data: {e}")
        # Fallback to another exchange if Kraken fails, e.g. Gate.io or just return empty
        try:
            print("Falling back to Gate.io...")
            exchange = ccxt.gateio()
            ohlcv = exchange.fetch_ohlcv("BTC/USDT", timeframe="1d", limit=1000)
            df = pd.DataFrame(
                ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"]
            )
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            return df
        except Exception as e2:
            print(f"Error fetching data from fallback: {e2}")
            return pd.DataFrame()


def determine_regime(df):
    if df.empty:
        return "Unknown"

    last_row = df.iloc[-1]
    price = last_row["close"]
    ema200 = last_row["ema200"]
    adx = last_row["adx"]

    # Logic:
    # Bull: Price > EMA200, ADX > 25
    # Sideways: ADX < 20
    # Volatile/Bear: Price < EMA200

    if price > ema200 and adx > 25:
        return "Bull"
    elif adx < 20:
        return "Sideways"
    elif price < ema200:
        return "Bear"
    else:
        return "Sideways"  # Default fallback for ambiguous cases


def update_config(regime):
    config_path = Path("user_data/configs/config_production.json")
    if not config_path.exists():
        print(f"Config file not found: {config_path}")
        return

    try:
        with config_path.open("r") as f:
            config = json.load(f)

        strategy = ""
        if regime == "Bull":
            strategy = "MomentumVolumeTrend"
        elif regime == "Sideways":
            strategy = "BollingerRSI"
        elif regime == "Bear":
            strategy = "VolatilityBreakout"
        else:
            strategy = "BollingerRSI"  # Fallback

        if config.get("strategy") != strategy:
            print(f"Switching strategy to {strategy} (Regime: {regime})")
            config["strategy"] = strategy
            with config_path.open("w") as f:
                json.dump(config, f, indent=4)
            log_change(regime, strategy)
        else:
            print(f"Strategy already set to {strategy} (Regime: {regime})")

    except Exception as e:
        print(f"Error updating config: {e}")


def log_change(regime, strategy):
    log_path = Path("regime_log.md")
    # Use UTC for logging
    now = datetime.now(UTC).strftime("%Y-%m-%d")
    entry = f"| {now} | {regime} | {strategy} |\n"

    if not log_path.exists():
        with log_path.open("w") as f:
            f.write("| Date | Regime | Strategy |\n|---|---|---|\n")

    with log_path.open("a") as f:
        f.write(entry)


def main():
    print("Fetching market data...")
    df = get_market_data()
    if df.empty:
        print("No data fetched. Exiting.")
        return

    print("Calculating indicators...")
    df["ema200"] = calculate_ema(df["close"], 200)
    df["adx"] = calculate_adx(df)

    # Use the last complete candle (iloc[-2]) or current candle (iloc[-1])?
    # Usually safer to use the last closed candle to avoid repainting during the day.
    # However, for regime detection on daily timeframe, using the latest close is often fine.

    last = df.iloc[-1]
    print(
        f"Latest Data: Close={last['close']}, "
        f"EMA200={last['ema200']:.2f}, ADX={last['adx']:.2f}"
    )

    regime = determine_regime(df)
    print(f"Detected Regime: {regime}")

    update_config(regime)


if __name__ == "__main__":
    main()
