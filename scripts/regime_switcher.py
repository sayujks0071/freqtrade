#!/usr/bin/env python3
"""
Regime Switcher Script
Analyzes BTC/USDT market conditions and updates the trading strategy in config_production.json.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import ccxt
import pandas as pd
import pandas_ta as ta


# Configuration
CONFIG_FILE = Path("user_data/configs/config_production.json")
LOG_FILE = Path("regime_log.md")
PAIR = "BTC/USDT"
TIMEFRAME = "1d"  # Daily analysis
LIMIT = 300  # Need at least 200 for EMA200 + some buffer


def get_market_data(pair, timeframe, limit):
    """
    Fetch OHLCV data from Delta (public API) or fallback to Kraken.
    """
    for exchange_id in ["delta", "kraken", "gateio"]:
        try:
            print(f"Fetching data from {exchange_id}...")
            exchange = getattr(ccxt, exchange_id)()
            ohlcv = exchange.fetch_ohlcv(pair, timeframe, limit=limit)
            if not ohlcv:
                continue
            df = pd.DataFrame(
                ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"]
            )
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            return df
        except Exception as e:
            print(f"Error fetching data from {exchange_id}: {e}")
            continue

    print("Failed to fetch data from all sources.")
    return pd.DataFrame()


def calculate_indicators(df):
    """
    Calculate EMA200 and ADX(14).
    """
    if df.empty:
        return df

    # EMA 200
    df["ema200"] = ta.ema(df["close"], length=200)

    # ADX 14
    adx = ta.adx(df["high"], df["low"], df["close"], length=14)
    # pandas_ta returns a DataFrame with ADX_14, DMP_14, DMN_14. We need ADX_14.
    # The column name is usually ADX_14.
    if adx is not None and not adx.empty:
        df = pd.concat([df, adx], axis=1)

    return df


def determine_regime(df):
    """
    Determine the market regime based on the latest indicators.
    """
    if df.empty or "ema200" not in df.columns or "ADX_14" not in df.columns:
        print("Insufficient data for indicators.")
        return None, None

    # Get latest closed candle (iloc[-1] is current open candle usually if fetching live,
    # but ccxt usually returns closed candles if using history, or latest.
    # However, for safety, let's use the last complete candle if we are mid-day?
    # Daily candle closes at UTC midnight. If we run this on Monday, we probably want
    # the candle that just closed (Sunday) or the current state.
    # Let's use the last row.
    latest = df.iloc[-1]

    price = latest["close"]
    ema200 = latest["ema200"]
    adx = latest["ADX_14"]

    print(f"Analysis for {latest['timestamp']}: Price={price}, EMA200={ema200}, ADX={adx}")

    if pd.isna(ema200) or pd.isna(adx):
        print("Indicators are NaN (not enough data?).")
        return None, None

    # Logic
    # Bull Market: Price > EMA200, ADX > 25
    if price > ema200 and adx > 25:
        return "Bull Market", "MomentumVolumeTrend"

    # Sideways/Choppy: ADX < 20
    elif adx < 20:
        return "Sideways/Choppy", "BollingerRSI"

    # Volatile/Crashing: Price < EMA200
    # Prompt says: Is it Volatile/Crashing? (VIX spike, Price < EMA200) -> VolatilityBreakout
    elif price < ema200:
        return "Volatile/Crashing", "VolatilityBreakout"

    # Default fallback (e.g. Price > EMA200 but ADX between 20 and 25)
    else:
        # Default to BollingerRSI (Sideways) as safe bet or stay previous.
        # Let's say Sideways for now as it's less risky than Momentum.
        return "Uncertain (Defaulting to Sideways)", "BollingerRSI"


def update_config(strategy_name):
    """
    Update the strategy in config_production.json.
    """
    if not CONFIG_FILE.exists():
        print(f"Config file {CONFIG_FILE} not found.")
        return False

    try:
        with CONFIG_FILE.open("r") as f:
            config = json.load(f)

        current_strategy = config.get("strategy")
        if current_strategy == strategy_name:
            print(f"Strategy is already {strategy_name}. No update needed.")
            return False

        config["strategy"] = strategy_name

        with CONFIG_FILE.open("w") as f:
            json.dump(config, f, indent=4)

        print(f"Updated config with strategy: {strategy_name}")
        return True

    except Exception as e:
        print(f"Error updating config: {e}")
        return False


def log_regime(regime, strategy):
    """
    Log the decision to regime_log.md.
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")  # noqa: UP017
    log_entry = f"| {timestamp} | {regime} | {strategy} |\n"

    if not LOG_FILE.exists():
        with LOG_FILE.open("w") as f:
            f.write("| Timestamp | Regime | Strategy |\n")
            f.write("|---|---|---|\n")

    with LOG_FILE.open("a") as f:
        f.write(log_entry)

    print(f"Logged: {regime} -> {strategy}")


def main():
    print("Starting Regime Detection...")
    df = get_market_data(PAIR, TIMEFRAME, LIMIT)
    if df.empty:
        print("Failed to get market data.")
        sys.exit(1)

    df = calculate_indicators(df)

    regime, strategy = determine_regime(df)

    if regime and strategy:
        print(f"Detected Regime: {regime}")
        print(f"Selected Strategy: {strategy}")

        update_config(strategy)
        log_regime(regime, strategy)
    else:
        print("Could not determine regime.")


if __name__ == "__main__":
    main()
