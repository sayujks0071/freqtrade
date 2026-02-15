import json
import traceback
from datetime import datetime
from pathlib import Path

import ccxt
import pandas as pd
import pandas_ta  # noqa: F401


def fetch_data():
    try:
        exchange = ccxt.kraken()
        # Kraken uses BTC/USD usually, but let's try to find a standard pair or use BTC/USD
        ohlcv = exchange.fetch_ohlcv("BTC/USD", "4h", limit=1000)
    except Exception:
        # Fallback to Gate.io if Kraken fails
        exchange = ccxt.gateio()
        ohlcv = exchange.fetch_ohlcv("BTC/USDT", "4h", limit=1000)

    df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df


def calculate_indicators(df):
    # Calculate EMA 200
    df.ta.ema(length=200, append=True)
    # Calculate ADX 14
    df.ta.adx(length=14, append=True)
    return df


def detect_regime(df):
    last_row = df.iloc[-1]
    close = last_row["close"]
    ema200 = last_row["EMA_200"]
    adx = last_row["ADX_14"]

    # Default
    regime = "Sideways/Choppy"
    strategy = "BollingerRSI"

    # Logic
    # Bull Market: Price > EMA200 AND ADX > 25
    if close > ema200 and adx > 25:
        regime = "Bull Market"
        strategy = "MomentumVolumeTrend"
    # Sideways/Choppy: ADX < 20
    elif adx < 20:
        regime = "Sideways/Choppy"
        strategy = "BollingerRSI"
    # Volatile/Crashing: Price < EMA200 (Bearish)
    elif close < ema200:
        regime = "Volatile/Crashing"
        strategy = "VolatilityBreakout"
    # Else default to BollingerRSI or keep previous
    # (here defaulting to BollingerRSI for safety/sideways assumption)

    return regime, strategy, close, ema200, adx


def update_config(strategy_name):
    config_path = Path("user_data/configs/config_production.json")
    if not config_path.exists():
        print(f"Config file not found: {config_path}")
        return False

    with config_path.open("r") as f:
        config = json.load(f)

    current_strategy = config.get("strategy")

    if current_strategy != strategy_name:
        print(f"Switching strategy from {current_strategy} to {strategy_name}")
        config["strategy"] = strategy_name
        with config_path.open("w") as f:
            json.dump(config, f, indent=4)
        return True
    else:
        print(f"Strategy already set to {strategy_name}")
        return False


def log_decision(regime, strategy, close, ema, adx):
    log_path = Path("regime_log.md")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = (
        f"| {timestamp} | {regime} | {strategy} | "
        f"Price: {close:.2f} | EMA200: {ema:.2f} | ADX: {adx:.2f} |\n"
    )

    if not log_path.exists():
        with log_path.open("w") as f:
            f.write("| Timestamp | Regime | Strategy | Metrics |\n")
            f.write("|---|---|---|---|\n")

    with log_path.open("a") as f:
        f.write(log_entry)


def main():
    try:
        print("Fetching data...")
        df = fetch_data()
        print("Calculating indicators...")
        df = calculate_indicators(df)

        if df["EMA_200"].isnull().iloc[-1] or df["ADX_14"].isnull().iloc[-1]:
            print("Not enough data for indicators.")
            return

        regime, strategy, close, ema, adx = detect_regime(df)

        print(f"Detected Regime: {regime}")
        print(f"Selected Strategy: {strategy}")

        update_config(strategy)
        log_decision(regime, strategy, close, ema, adx)
        print("Done.")

    except Exception as e:
        print(f"Error: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    main()
