#!/usr/bin/env python3
"""
Regime Switcher Script
Analyzes BTC/USDT market data to determine the current market regime
and updates the production configuration with the appropriate strategy.
"""

import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

import ccxt
import pandas as pd
import talib.abstract as ta


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Constants
CONFIG_PATH = (
    Path(__file__).resolve().parent.parent / "user_data" / "configs" / "config_production.json"
)
LOG_PATH = Path(__file__).resolve().parent.parent / "regime_log.md"
PAIR = "BTC/USDT"
TIMEFRAME = "1d"
LIMIT = 1000  # Need enough data for EMA200 + warmup


def fetch_data():
    """Fetch daily OHLCV data for BTC/USDT."""
    exchange = ccxt.kraken(
        {
            "timeout": 30000,
            "enableRateLimit": True,
        }
    )
    try:
        # fetch_ohlcv returns list of [timestamp, open, high, low, close, volume]
        ohlcv = exchange.fetch_ohlcv(PAIR, timeframe=TIMEFRAME, limit=LIMIT)
        df = pd.DataFrame(ohlcv, columns=["date", "open", "high", "low", "close", "volume"])
        df["date"] = pd.to_datetime(df["date"], unit="ms")
        return df
    except Exception as e:
        logger.error(f"Error fetching data: {e}")
        sys.exit(1)


def calculate_indicators(df):
    """Calculate EMA200, ADX."""
    # Ensure we have enough data
    if len(df) < 200:
        logger.error("Not enough data to calculate EMA200")
        sys.exit(1)

    df["ema200"] = ta.EMA(df, timeperiod=200)
    df["adx"] = ta.ADX(df, timeperiod=14)
    return df


def determine_regime(df):
    """
    Determine regime based on latest indicators.
    Bull: Price > EMA200, ADX > 25
    Sideways: ADX < 20
    Volatile/Bear: Price < EMA200
    """
    last_row = df.iloc[-1]
    price = last_row["close"]
    ema200 = last_row["ema200"]
    adx = last_row["adx"]

    logger.info(f"Current Market Data: Price={price:.2f}, EMA200={ema200:.2f}, ADX={adx:.2f}")

    if adx < 20:
        return "Sideways", "BollingerRSI"
    elif price > ema200:
        if adx > 25:
            return "Bull", "MomentumVolumeTrend"
        else:
            # Weak Bull
            return "Bull (Weak)", "MomentumVolumeTrend"
    else:
        # Price < EMA200 -> Bear/Volatile
        return "Volatile/Bear", "VolatilityBreakout"


def update_config(strategy_name):
    """Update the strategy in config_production.json."""
    if not CONFIG_PATH.exists():
        logger.error(f"Config file not found at {CONFIG_PATH}")
        sys.exit(1)

    with CONFIG_PATH.open("r") as f:
        config = json.load(f)

    current_strategy = config.get("strategy")

    if current_strategy == strategy_name:
        logger.info(f"Strategy is already {strategy_name}. No change needed.")
        return False

    logger.info(f"Switching strategy from {current_strategy} to {strategy_name}")
    config["strategy"] = strategy_name

    with CONFIG_PATH.open("w") as f:
        json.dump(config, f, indent=4)

    return True


def log_regime(regime, strategy_name, changed):
    """Log the decision to regime_log.md."""
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    action = "Switched to" if changed else "Maintained"

    log_entry = f"| {timestamp} | {regime} | {action} {strategy_name} |\n"

    if not LOG_PATH.exists():
        with LOG_PATH.open("w") as f:
            f.write("# Regime Switcher Log\n\n")
            f.write("| Timestamp | Regime | Action |\n")
            f.write("| --- | --- | --- |\n")

    with LOG_PATH.open("a") as f:
        f.write(log_entry)


def main():
    logger.info("Starting Regime Analysis...")
    df = fetch_data()
    df = calculate_indicators(df)
    regime, strategy = determine_regime(df)

    logger.info(f"Detected Regime: {regime}")
    changed = update_config(strategy)
    log_regime(regime, strategy, changed)
    logger.info("Regime Analysis Complete.")


if __name__ == "__main__":
    main()
