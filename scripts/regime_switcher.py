#!/usr/bin/env python3
"""
Regime Switcher Script
Analyzes BTC/USDT market data to detect regime (Bull, Sideways, Volatile)
and updates the strategy configuration.
"""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path


try:
    import ccxt
    import pandas as pd
    import talib
except ImportError as e:
    print(f"Error importing dependencies: {e}")
    sys.exit(1)

# Configuration
USER_DATA_DIR = Path("user_data")
CONFIG_FILE = USER_DATA_DIR / "configs/config_production.json"
BASE_CONFIG_FILE = USER_DATA_DIR / "configs/config.delta.dryrun.json"
LOG_FILE = Path("regime_log.md")

# Market Parameters
# Using Kraken BTC/USD as a reliable source for BTC price action
EXCHANGE_ID = "kraken"
PAIR = "BTC/USD"
TIMEFRAME = "1d"
LIMIT = 1000  # Ensure enough warmup for EMA200


def get_market_data():
    """Fetches OHLCV data from Kraken."""
    try:
        exchange = getattr(ccxt, EXCHANGE_ID)()
        ohlcv = exchange.fetch_ohlcv(PAIR, timeframe=TIMEFRAME, limit=LIMIT)
        df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        return df
    except Exception as e:
        print(f"Error fetching data from {EXCHANGE_ID}: {e}")
        # Fallback to Gate.io if Kraken fails
        try:
            print("Attempting fallback to gateio...")
            exchange = ccxt.gateio()
            # Gate.io uses BTC/USDT
            ohlcv = exchange.fetch_ohlcv("BTC/USDT", timeframe=TIMEFRAME, limit=LIMIT)
            df = pd.DataFrame(
                ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"]
            )
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            return df
        except Exception as e2:
            print(f"Error fetching data from fallback: {e2}")
            return None


def analyze_regime(df):
    """
    Analyzes the dataframe to determine the market regime.
    Returns: (Regime Name, Strategy Name, Metrics Dict)
    """
    if df is None or df.empty:
        return None, None, {}

    # Calculate Indicators
    # EMA 200
    df["ema200"] = talib.EMA(df["close"], timeperiod=200)
    # ADX 14
    df["adx"] = talib.ADX(df["high"], df["low"], df["close"], timeperiod=14)

    # Get latest values
    # Ensure we have valid data (drop NaNs from start)
    df = df.dropna()
    if df.empty:
        return None, None, {}

    last_row = df.iloc[-1]

    price = last_row["close"]
    ema200 = last_row["ema200"]
    adx = last_row["adx"]

    metrics = {"price": price, "ema200": ema200, "adx": adx}

    # Logic
    # Bull Market: Price > EMA200, ADX > 25 -> Activate MomentumVolumeTrend.
    # Sideways/Choppy: ADX < 20 -> Activate BollingerRSI.
    # Volatile/Crashing: Price < EMA200 -> Activate VolatilityBreakout.
    # Note: VIX spike detection is omitted due to lack of standard crypto VIX
    # data in CCXT. We rely on Price < EMA200 for bearish/volatile conditions.

    regime = "Unknown"
    strategy = None

    if price > ema200 and adx > 25:
        regime = "Bull"
        strategy = "MomentumVolumeTrend"
    elif adx < 20:
        regime = "Sideways"
        strategy = "BollingerRSI"
    elif price < ema200:
        regime = "Volatile/Bear"
        strategy = "VolatilityBreakout"
    else:
        # Fallback logic for undefined states
        if price > ema200:
            regime = "Bull (Weak Trend)"
            strategy = "MomentumVolumeTrend"
        else:
            regime = "Volatile/Bear (Weak)"
            strategy = "VolatilityBreakout"

    return regime, strategy, metrics


def update_config(strategy_name):
    """Updates the production config file with the new strategy."""
    config = {}

    # Load base or existing config
    if CONFIG_FILE.exists():
        with CONFIG_FILE.open("r") as f:
            try:
                config = json.load(f)
            except json.JSONDecodeError:
                print(f"Error decoding {CONFIG_FILE}, starting fresh/from base.")
                config = {}

    if not config and BASE_CONFIG_FILE.exists():
        with BASE_CONFIG_FILE.open("r") as f:
            config = json.load(f)
            # Ensure not dry_run if this is production?
            # The prompt implies switching config_production.json.
            # I should probably assume config_production.json might be live.
            # But I shouldn't change dry_run flag unless asked.
            # Just updating strategy.

    if not config:
        print("Warning: No base config found. Creating minimal config.")
        config = {"strategy": strategy_name}

    # Update Strategy
    config["strategy"] = strategy_name

    # Ensure the directory exists
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)

    with CONFIG_FILE.open("w") as f:
        json.dump(config, f, indent=4)


def log_decision(regime, strategy, metrics):
    """Logs the decision to regime_log.md"""
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

    log_entry = f"""
## {timestamp}
- **Regime:** {regime}
- **Strategy:** {strategy}
- **Metrics:**
  - Price: {metrics.get("price", 0):.2f}
  - EMA200: {metrics.get("ema200", 0):.2f}
  - ADX: {metrics.get("adx", 0):.2f}
---
"""
    with LOG_FILE.open("a") as f:
        f.write(log_entry)


def main():
    print("Starting Regime Detection...")
    df = get_market_data()
    if df is None:
        print("Failed to get market data.")
        sys.exit(1)

    regime, strategy, metrics = analyze_regime(df)

    if strategy:
        print(f"Detected Regime: {regime}")
        print(f"Switching to Strategy: {strategy}")
        print(
            f"Metrics: Price={metrics.get('price'):.2f}, "
            f"EMA200={metrics.get('ema200'):.2f}, ADX={metrics.get('adx'):.2f}"
        )
        update_config(strategy)
        log_decision(regime, strategy, metrics)
        print("Config updated and logged.")
    else:
        print("Could not determine regime.")
        sys.exit(1)


if __name__ == "__main__":
    main()
