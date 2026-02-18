#!/usr/bin/env python3
"""
Regime Switcher Script
Analyzes BTC/USDT market data and updates the active strategy in config_production.json.
"""

import argparse
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

import ccxt
import pandas as pd
import pandas_ta as ta  # noqa: F401


# Configuration
USER_DATA_DIR = Path("user_data")
CONFIG_DIR = USER_DATA_DIR / "configs"
# Default source config (can be overridden)
DEFAULT_CONFIG_SOURCE = CONFIG_DIR / "config.delta.live.json"
# Target config file
CONFIG_TARGET = USER_DATA_DIR / "config_production.json"
REGIME_LOG = USER_DATA_DIR / "regime_log.md"

# Strategy Names
STRATEGY_BULL = "MomentumVolumeTrend"
STRATEGY_SIDEWAYS = "BollingerRSI"
STRATEGY_VOLATILE = "VolatilityBreakout"

# Market Analysis Config
PAIR = "BTC/USDT"
TIMEFRAME = "1d"
LIMIT = 300  # Enough for EMA200
EXCHANGE_ID = "gateio"  # Using gateio public api


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    return logging.getLogger(__name__)


logger = setup_logging()


def fetch_data(exchange_id, symbol, timeframe, limit):
    try:
        exchange_class = getattr(ccxt, exchange_id)
        exchange = exchange_class()
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        return df
    except Exception as e:
        logger.error(f"Error fetching data from {exchange_id}: {e}")
        return pd.DataFrame()


def calculate_indicators(df):
    if df.empty:
        return df

    # Calculate indicators using pandas_ta
    df.ta.ema(length=200, append=True)
    df.ta.adx(length=14, append=True)
    df.ta.atr(length=14, append=True)

    # Calculate Volatility Spike
    # Using ATR relative to its SMA(20)
    # pandas_ta usually names ATR as ATRr_14 or ATR_14 depending on version.
    # We check columns to be sure or use logic
    atr_col = "ATRr_14" if "ATRr_14" in df.columns else "ATR_14"
    if atr_col not in df.columns:
        logger.warning(f"ATR column not found. Columns: {df.columns}")
        return df

    df["atr_sma"] = df[atr_col].rolling(window=20).mean()
    df["volatility_spike"] = df[atr_col] > (df["atr_sma"] * 1.5)

    return df


def determine_regime(row):
    # row is the last row of the dataframe
    close = row["close"]
    ema200 = row.get("EMA_200")
    adx = row.get("ADX_14")
    volatility_spike = row.get("volatility_spike", False)

    if pd.isna(ema200) or pd.isna(adx):
        logger.warning("Indicators are NaN. defaulting to Sideways.")
        return "Sideways (Data Error)", STRATEGY_SIDEWAYS

    # Logic
    # 1. Volatile/Crashing: Price < EMA200 AND Volatility Spike
    if close < ema200 and volatility_spike:
        return "Volatile", STRATEGY_VOLATILE

    # 2. Bull Market: Price > EMA200 AND ADX > 25
    elif close > ema200 and adx > 25:
        return "Bull", STRATEGY_BULL

    # 3. Sideways/Choppy: ADX < 20
    elif adx < 20:
        return "Sideways", STRATEGY_SIDEWAYS

    # 4. Transitional / Weak
    else:
        if close > ema200:
            return "Bull (Weak)", STRATEGY_BULL
        else:
            # Bearish but not volatile enough for breakout? Or default to breakout anyway?
            # Or default to Sideways?
            # Prompt says: "Volatile/Crashing? (VIX spike, Price < EMA200)"
            # If Price < EMA200 but no spike, maybe just weak bear.
            # I'll default to Sideways for safety or Volatile if it handles shorts better.
            # Let's use VolatileBreakout as it has short logic which is good for < EMA200.
            return "Bear (Weak)", STRATEGY_VOLATILE


def update_config(strategy_name, config_source):
    # Load source config
    if not config_source.exists():
        logger.error(f"Source config {config_source} not found.")
        return False

    try:
        with config_source.open() as f:
            config = json.load(f)

        # Update strategy
        config["strategy"] = strategy_name

        # Write to target config
        with CONFIG_TARGET.open("w") as f:
            json.dump(config, f, indent=4)

        logger.info(f"Updated {CONFIG_TARGET} with strategy: {strategy_name}")
        return True
    except Exception as e:
        logger.error(f"Error updating config: {e}")
        return False


def log_regime(regime, strategy):
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    message = f"| {timestamp} | {regime} | {strategy} |\n"

    if not REGIME_LOG.exists():
        with REGIME_LOG.open("w") as f:
            f.write("| Timestamp | Regime | Strategy |\n")
            f.write("|---|---|---|\n")

    with REGIME_LOG.open("a") as f:
        f.write(message)

    logger.info(f"Logged regime: {regime} -> {strategy}")


def main():
    parser = argparse.ArgumentParser(description="Regime Switcher Script")
    parser.add_argument("--dry-run", action="store_true", help="Do not update config")
    parser.add_argument("--config", type=str, default=None, help="Path to source config file")
    args = parser.parse_args()

    logger.info("Starting Regime Analysis...")

    # Determine config source
    if args.config:
        config_source = Path(args.config)
    elif DEFAULT_CONFIG_SOURCE.exists():
        config_source = DEFAULT_CONFIG_SOURCE
    elif CONFIG_TARGET.exists():
        logger.info(f"Default source not found, using {CONFIG_TARGET} as source.")
        config_source = CONFIG_TARGET
    else:
        logger.error("No valid config file found to use as template.")
        sys.exit(1)

    # 1. Fetch Data
    df = fetch_data(EXCHANGE_ID, PAIR, TIMEFRAME, LIMIT)
    if df.empty:
        logger.error("Failed to fetch data. Exiting.")
        sys.exit(1)

    # 2. Calculate Indicators
    df = calculate_indicators(df)
    if df.empty or "EMA_200" not in df.columns:
        logger.error("Failed to calculate indicators. Exiting.")
        sys.exit(1)

    # 3. Determine Regime (using last closed candle)
    # fetch_ohlcv returns candles including the current open one usually.
    # So -2 is the last fully closed candle.
    if len(df) < 2:
        logger.error("Not enough data.")
        sys.exit(1)

    last_row = df.iloc[-2]

    regime, strategy = determine_regime(last_row)

    logger.info(f"Detected Regime: {regime}")
    logger.info(f"Selected Strategy: {strategy}")

    # 4. Update Config
    if not args.dry_run:
        success = update_config(strategy, config_source)
        if success:
            log_regime(regime, strategy)
        else:
            sys.exit(1)
    else:
        logger.info("Dry run: Config not updated.")


if __name__ == "__main__":
    main()
