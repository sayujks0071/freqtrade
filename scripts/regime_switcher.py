#!/usr/bin/env python3
"""
Regime Switcher Script
Analyzes market conditions for BTC/USDT and switches the active strategy in config_production.json.
"""

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import ccxt
import pandas as pd
import pandas_ta as ta


try:
    from datetime import UTC
except ImportError:
    from datetime import timezone

    UTC = timezone.utc  # noqa: UP017


# Constants
CONFIG_PATH = Path("user_data/configs/config_production.json")
LOG_FILE = Path("regime_log.md")
PAIR = "BTC/USDT"
TIMEFRAME = "1d"  # Daily candles for regime detection
LIMIT = 300  # Enough data for EMA200

# Setup Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def fetch_data():
    """Fetches OHLCV data for BTC/USDT from a public exchange (using Kraken or Binance as proxy)."""
    # Using Kraken as it usually has good public API availability without keys
    exchange = ccxt.kraken()
    try:
        ohlcv = exchange.fetch_ohlcv(PAIR, timeframe=TIMEFRAME, limit=LIMIT)
        df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        return df
    except Exception as e:
        logger.error(f"Error fetching data: {e}")
        sys.exit(1)


def detect_regime(df):
    """
    Analyzes the dataframe to determine the current market regime.

    Rules:
    - Bull Market: Price > EMA200 and ADX > 25 -> MomentumVolumeTrend
    - Sideways/Choppy: ADX < 20 -> BollingerRSI
    - Volatile/Crashing: Price < EMA200 and High Volatility -> VolatilityBreakout
    """
    # Calculate Indicators
    df["ema200"] = ta.ema(df["close"], length=200)
    adx_df = ta.adx(df["high"], df["low"], df["close"], length=14)
    # pandas_ta ADX returns a DF with ADX_14, DMP_14, DMN_14. We need ADX_14.
    df["adx"] = adx_df["ADX_14"]

    # Calculate Volatility (ATR normalized by price)
    df["atr"] = ta.atr(df["high"], df["low"], df["close"], length=14)
    df["atr_pct"] = df["atr"] / df["close"]

    # Get last row
    last = df.iloc[-1]

    price = last["close"]
    ema200 = last["ema200"]
    adx = last["adx"]
    atr_pct = last["atr_pct"]

    logger.info(
        f"Indicators: Price={price:.2f}, EMA200={ema200:.2f}, ADX={adx:.2f}, ATR%={atr_pct:.4f}"
    )

    # Logic
    # 1. Volatile/Crashing: Price < EMA200 and High Volatility
    # What is "High Volatility"? Let's assume ATR% > 0.05 (5% daily move) or similar.
    # For daily timeframe, 5% is quite high.
    if price < ema200 and atr_pct > 0.04:
        return "VolatilityBreakout", "Volatile/Crashing"

    # 2. Bull Market: Price > EMA200 and ADX > 25
    if price > ema200 and adx > 25:
        return "MomentumVolumeTrend", "Bull Market"

    # 3. Sideways/Choppy: ADX < 20
    if adx < 20:
        return "BollingerRSI", "Sideways/Choppy"

    # Default fallback (if none match, e.g. ADX between 20-25 or Price < EMA200 but low vol)
    # If Price < EMA200 and low vol, it's a Bear Market but not crashing.
    # Maybe VolatilityBreakout is still safer if enabled for shorts, or keep current.
    # For now, let's default to BollingerRSI for "uncertain/ranging"
    # or MomentumVolumeTrend if trending?
    # Let's default to DeltaSafeStrategy (the original one) or stick to BollingerRSI as safe haven.
    return "BollingerRSI", "Uncertain/Bearish (Low Vol)"


def update_config(strategy_name, regime_name):
    """Updates the config_production.json file with the selected strategy."""
    if not CONFIG_PATH.exists():
        logger.error(f"Config file not found: {CONFIG_PATH}")
        sys.exit(1)

    with CONFIG_PATH.open() as f:
        config = json.load(f)

    current_strategy = config.get("strategy")

    if current_strategy == strategy_name:
        logger.info(f"Strategy is already {strategy_name}. No change needed.")
        return

    config["strategy"] = strategy_name

    # Update unidirectional_only based on strategy
    if strategy_name == "VolatilityBreakout":
        config["unidirectional_only"] = False
        logger.info("Enabled Shorting (unidirectional_only=False)")
    else:
        # Default to True for other strategies if they are long-only?
        # MomentumVolumeTrend is Long only. BollingerRSI is Long only.
        config["unidirectional_only"] = True
        logger.info("Disabled Shorting (unidirectional_only=True)")

    with CONFIG_PATH.open("w") as f:
        json.dump(config, f, indent=4)

    logger.info(f"Switched strategy to {strategy_name}")
    log_decision(strategy_name, regime_name)


def log_decision(strategy_name, regime_name):
    """Appends the decision to the regime_log.md file."""
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    message = f"| {timestamp} | {regime_name} | Switched to `{strategy_name}` |"

    # Check if header exists
    header = "| Timestamp | Regime | Action |\n|---|---|---|\n"

    if not LOG_FILE.exists():
        with LOG_FILE.open("w") as f:
            f.write("# Regime Switch Log\n\n" + header)

    with LOG_FILE.open("a") as f:
        f.write(message + "\n")


def main():
    logger.info("Starting Regime Detection...")
    df = fetch_data()
    strategy, regime = detect_regime(df)
    logger.info(f"Detected Regime: {regime} -> Strategy: {strategy}")
    update_config(strategy, regime)
    logger.info("Done.")


if __name__ == "__main__":
    main()
