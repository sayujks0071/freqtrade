#!/usr/bin/env python3
"""
Regime Switcher Script
Analyzes BTC/USDT market data to detect regime and update strategy config.
Regimes:
- Bull: Price > EMA200 (and ADX > 25) -> MomentumVolumeTrend
- Sideways: ADX < 20 -> BollingerRSI
- Volatile/Bear: Price < EMA200 -> VolatilityBreakout
"""

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import ccxt
import pandas as pd
import talib.abstract as ta

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("regime_switcher")


def get_market_data(pair="BTC/USDT", timeframe="1d", limit=300):
    """Fetch OHLCV data from Binance (or fallback)."""
    # Use Binance for consistent data
    exchange = ccxt.binance()
    try:
        ohlcv = exchange.fetch_ohlcv(pair, timeframe=timeframe, limit=limit)
        df = pd.DataFrame(
            ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"]
        )
        # Convert timestamp
        df["date"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        return df
    except Exception as e:
        logger.error(f"Error fetching data: {e}")
        sys.exit(1)


def detect_regime(df):
    """
    Detect market regime based on indicators.
    Returns: (regime_name, strategy_name, allow_short)
    """
    # Calculate indicators
    df["ema200"] = ta.EMA(df, timeperiod=200)
    df["adx"] = ta.ADX(df, timeperiod=14)

    last_row = df.iloc[-1]
    close = last_row["close"]
    ema200 = last_row["ema200"]
    adx = last_row["adx"]

    logger.info(
        f"Analysis for {last_row['date']}: Close={close:.2f}, EMA200={ema200:.2f}, ADX={adx:.2f}"
    )

    # Logic
    if adx < 20:
        return "Sideways", "BollingerRSI", False
    elif close < ema200:
        return "Volatile/Bear", "VolatilityBreakout", True
    elif close > ema200 and adx > 25:
        return "Bull", "MomentumVolumeTrend", False
    else:
        # Fallback for "Price > EMA200 but 20 <= ADX <= 25"
        # We default to MomentumVolumeTrend as we are above EMA200
        logger.info("Regime ambiguous (Bullish bias), defaulting to MomentumVolumeTrend")
        return "Bull (Weak)", "MomentumVolumeTrend", False


def update_config(strategy_name, allow_short):
    """Update config_production.json."""
    # Use parents[1] to avoid potential issues with .parent.parent in tests or odd environments
    config_path = (
        Path(__file__).resolve().parents[1] / "user_data/configs/config_production.json"
    )
    if not config_path.exists():
        logger.error(f"Config not found at {config_path}")
        sys.exit(1)

    try:
        with config_path.open("r") as f:
            config = json.load(f)

        config["strategy"] = strategy_name
        config["unidirectional_only"] = not allow_short

        # If we enable shorts, we should ensure trading_mode is futures (it is in template)

        with config_path.open("w") as f:
            json.dump(config, f, indent=4)

        logger.info(
            f"Updated config with strategy={strategy_name}, unidirectional_only={not allow_short}"
        )

    except Exception as e:
        logger.error(f"Error updating config: {e}")
        sys.exit(1)


def log_decision(regime, strategy):
    """Log decision to regime_log.md."""
    log_path = Path(__file__).resolve().parents[1] / "regime_log.md"

    timestamp = datetime.now(timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S UTC"
    )  # noqa: UP017
    message = f"| {timestamp} | {regime} | Switched to {strategy} |"

    # Create header if missing
    if not log_path.exists():
        with log_path.open("w") as f:
            f.write("| Date | Regime | Action |\n")
            f.write("|---|---|---|\n")

    with log_path.open("a") as f:
        f.write(message + "\n")

    logger.info(f"Logged: {message}")


def main():
    logger.info("Starting Regime Switcher...")

    # 1. Get Data
    df = get_market_data()

    # 2. Detect Regime
    regime, strategy, allow_short = detect_regime(df)
    logger.info(f"Detected Regime: {regime} -> Strategy: {strategy}")

    # 3. Update Config
    update_config(strategy, allow_short)

    # 4. Log
    log_decision(regime, strategy)

    logger.info("Regime Switcher completed successfully.")


if __name__ == "__main__":
    main()
