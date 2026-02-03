#!/usr/bin/env python3
"""
Regime Switcher Script
Analyzes BTC/USDT market conditions and switches the active strategy in config_production.json.
"""

import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

import ccxt
import pandas as pd
import talib.abstract as ta


# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Constants
PAIR = "BTC/USDT"
TIMEFRAME = "1d"
LIMIT = 250  # Enough for EMA 200 warmup
CONFIG_TEMPLATE_PATH = Path("user_data/configs/config.delta.dryrun.json")
CONFIG_PROD_PATH = Path("user_data/configs/config_production.json")
LOG_FILE = Path("regime_log.md")


def fetch_data():
    """Fetch OHLCV data for BTC/USDT from Gate.io."""
    try:
        exchange = ccxt.gateio()
        # Fetch candles
        ohlcv = exchange.fetch_ohlcv(PAIR, timeframe=TIMEFRAME, limit=LIMIT)
        df = pd.DataFrame(ohlcv, columns=["date", "open", "high", "low", "close", "volume"])
        df["date"] = pd.to_datetime(df["date"], unit="ms", utc=True)
        return df
    except Exception as e:
        logger.error(f"Error fetching data: {e}")
        sys.exit(1)


def calculate_indicators(df):
    """Calculate EMA 200 and ADX 14."""
    df["ema_200"] = ta.EMA(df, timeperiod=200)
    df["adx"] = ta.ADX(df, timeperiod=14)
    return df


def detect_regime(df):
    """
    Detect market regime based on the latest closed candle.
    Returns: (Regime Name, Strategy Name)
    """
    # Use the last completed candle (second to last row)
    last_candle = df.iloc[-2]

    # Check if data is sufficient
    if pd.isna(last_candle["ema_200"]) or pd.isna(last_candle["adx"]):
        logger.warning("Not enough data for indicators. Defaulting to VolatilityBreakout.")
        return "Unknown/Insufficient Data", "VolatilityBreakout"

    close = last_candle["close"]
    ema_200 = last_candle["ema_200"]
    adx = last_candle["adx"]

    logger.info(
        f"Analysis - Date: {last_candle['date']}, Price: {close}, EMA200: {ema_200}, ADX: {adx}"
    )

    if close > ema_200 and adx > 25:
        return "Bull Market", "MomentumVolumeTrend"
    elif adx < 20:
        return "Sideways/Choppy", "BollingerRSI"
    else:
        # Default fallback or Bear conditions
        return "Bear/Volatile", "VolatilityBreakout"


def update_config(strategy_name):
    """Update config_production.json with the new strategy."""
    # Load template or existing prod config
    if CONFIG_PROD_PATH.exists():
        with CONFIG_PROD_PATH.open() as f:
            config = json.load(f)
    else:
        if CONFIG_TEMPLATE_PATH.exists():
            with CONFIG_TEMPLATE_PATH.open() as f:
                config = json.load(f)
        else:
            logger.error(f"Template config not found at {CONFIG_TEMPLATE_PATH}")
            sys.exit(1)

    # Update strategy
    config["strategy"] = strategy_name

    # Write back
    with CONFIG_PROD_PATH.open("w") as f:
        json.dump(config, f, indent=4)

    logger.info(f"Updated {CONFIG_PROD_PATH} with strategy: {strategy_name}")


def log_decision(regime, strategy_name):
    """Log the decision to regime_log.md."""
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    log_entry = f"| {timestamp} | {regime} | Switched to: {strategy_name} |\n"

    if not LOG_FILE.exists():
        with LOG_FILE.open("w") as f:
            f.write("| Timestamp | Regime | Action |\n")
            f.write("|---|---|---|\n")

    with LOG_FILE.open("a") as f:
        f.write(log_entry)

    logger.info(f"Logged decision: {regime} -> {strategy_name}")


def main():
    logger.info("Starting Regime Switcher...")
    df = fetch_data()
    df = calculate_indicators(df)
    regime, strategy = detect_regime(df)

    logger.info(f"Detected Regime: {regime}")
    logger.info(f"Selected Strategy: {strategy}")

    update_config(strategy)
    log_decision(regime, strategy)
    logger.info("Done.")


if __name__ == "__main__":
    main()
