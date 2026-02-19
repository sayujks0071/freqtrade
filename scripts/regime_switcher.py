#!/usr/bin/env python3
"""
Regime Switcher Script
Analyzes BTC/USDT market data to determine the current market regime
and updates the active strategy in the configuration.
"""

import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

import ccxt
import pandas as pd
import pandas_ta as ta  # noqa: F401


# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("RegimeSwitcher")

# Configuration
USER_DATA_DIR = Path("user_data")
CONFIG_SOURCE = USER_DATA_DIR / "configs/config.delta.live.json"
CONFIG_TARGET = USER_DATA_DIR / "config_production.json"
LOG_FILE = Path("regime_log.md")

# Strategy Mapping
STRATEGY_BULL = "MomentumVolumeTrend"
STRATEGY_BEAR = "VolatilityBreakout"
STRATEGY_SIDEWAYS = "BollingerRSI"


def get_btc_data():
    """
    Fetch daily BTC/USDT data from Gate.io (public API).
    """
    try:
        exchange = ccxt.gateio()
        # Fetch enough candles for EMA200
        ohlcv = exchange.fetch_ohlcv("BTC/USDT", timeframe="1d", limit=300)

        if not ohlcv:
            logger.error("No data received from exchange.")
            return None

        df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["date"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        return df
    except Exception as e:
        logger.error(f"Error fetching data: {e}")
        return None


def analyze_market(df):
    """
    Analyze market data to determine regime.
    """
    # Calculate Indicators
    # EMA 200
    df["ema200"] = df.ta.ema(length=200)
    # ADX 14
    adx = df.ta.adx(length=14)
    # pandas_ta ADX returns a DF with ADX_14, DMP_14, DMN_14. We need ADX_14.
    # The column name is typically ADX_14
    df["adx"] = adx["ADX_14"]

    # Get last closed candle (second to last row, as last row is current/open candle)
    # Wait, fetch_ohlcv returns closed candles usually? No, it returns up to current time.
    # The last candle might be incomplete.
    # Safe to use the last completed candle (-2) or just assume -1 if running at 00:00 UTC
    # and daily close just happened.
    # I'll use -2 to be safe against open candle volatility, or -1 if I'm sure it's closed.
    # Since this runs at 00:00 UTC Monday, the daily candle for Sunday just closed.
    # So -1 (index -1) should be the Sunday candle if fetch_ohlcv includes it.
    # Usually exchanges return the current open candle as the last one.
    # So -2 is the last FULLY CLOSED candle.

    last_candle = df.iloc[-2]

    close = last_candle["close"]
    ema200 = last_candle["ema200"]
    adx_val = last_candle["adx"]

    logger.info(f"Analysis Date: {last_candle['date']}")
    logger.info(f"Close: {close}, EMA200: {ema200}, ADX: {adx_val}")

    if pd.isna(ema200) or pd.isna(adx_val):
        logger.warning("Not enough data for indicators.")
        return None, None

    # Determine Regime
    regime = "Unknown"
    strategy = STRATEGY_SIDEWAYS  # Default

    if close < ema200:
        # Bear/Volatile Regime
        # Note: The prompt mentioned "VIX spike", but VIX data is not natively available via CCXT.
        # We use Price < EMA200 as a proxy for Bear/Risk-Off conditions,
        # often associated with volatility.
        regime = "Bear/Volatile"
        strategy = STRATEGY_BEAR
    elif (close > ema200) and (adx_val > 25):
        regime = "Bull"
        strategy = STRATEGY_BULL
    else:
        # close > ema200 but adx <= 25 OR close just around ema?
        # Actually my logic was:
        # if close < ema200 -> Bear
        # elif adx < 25 -> Sideways (This covers close > ema200 AND adx < 25)
        # else -> Bull (close > ema200 AND adx >= 25)

        # Re-evaluating logic based on prompt gaps:
        # Bear: close < ema200
        # Bull: close > ema200 AND adx > 25
        # Sideways: The rest.

        regime = "Sideways/Weak"
        strategy = STRATEGY_SIDEWAYS

    return regime, strategy


def update_config(strategy_name):
    """
    Update the configuration file with the new strategy.
    """
    # Load Source Config or Target if exists?
    # Strategy says: "Update config_production.json".
    # I'll try to load config_production.json first to preserve other settings.
    # If not found, load config.delta.live.json.

    config_data = {}
    source_used = CONFIG_TARGET

    if CONFIG_TARGET.exists():
        try:
            with CONFIG_TARGET.open() as f:
                config_data = json.load(f)
        except Exception as e:
            logger.error(f"Error reading {CONFIG_TARGET}: {e}")
            # Fallback
            source_used = CONFIG_SOURCE
    else:
        source_used = CONFIG_SOURCE

    if not config_data and source_used.exists():
        try:
            with source_used.open() as f:
                config_data = json.load(f)
        except Exception as e:
            logger.error(f"Error reading {source_used}: {e}")
            return False

    if not config_data:
        logger.error("No configuration found.")
        return False

    # Update Strategy
    config_data["strategy"] = strategy_name

    # Write to Target
    try:
        with CONFIG_TARGET.open("w") as f:
            json.dump(config_data, f, indent=4)
        logger.info(f"Updated {CONFIG_TARGET} with strategy: {strategy_name}")
        return True
    except Exception as e:
        logger.error(f"Error writing to {CONFIG_TARGET}: {e}")
        return False


def log_decision(regime, strategy):
    """
    Log the decision to regime_log.md
    """
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    message = f"| {timestamp} | {regime} | {strategy} |"

    # Check if file exists and has header
    file_exists = LOG_FILE.exists()

    try:
        with LOG_FILE.open("a") as f:
            if not file_exists:
                f.write("| Timestamp | Regime | Strategy |\n")
                f.write("| --- | --- | --- |\n")
            f.write(message + "\n")
        logger.info(f"Logged decision: {message}")
    except Exception as e:
        logger.error(f"Error logging decision: {e}")


def main():
    logger.info("Starting Regime Detection...")

    df = get_btc_data()
    if df is None or df.empty:
        logger.error("Failed to get data. Exiting.")
        sys.exit(1)

    regime, strategy = analyze_market(df)

    if not regime or not strategy:
        logger.error("Failed to determine regime. Exiting.")
        sys.exit(1)

    logger.info(f"Detected Regime: {regime}")
    logger.info(f"Selected Strategy: {strategy}")

    if update_config(strategy):
        log_decision(regime, strategy)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
