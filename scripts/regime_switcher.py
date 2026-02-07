#!/usr/bin/env python3
"""
Regime Switcher Script
Analyzes market conditions (BTC/USDT) and updates the active strategy in config_production.json.
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
logger = logging.getLogger("RegimeSwitcher")


def get_project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def fetch_market_data(pair="BTC/USDT", timeframe="1d", limit=300):
    """
    Fetch OHLCV data from Kucoin.
    """
    try:
        exchange = ccxt.kucoin()
        ohlcv = exchange.fetch_ohlcv(pair, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["date"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        return df
    except Exception as e:
        logger.error(f"Error fetching market data: {e}")
        return pd.DataFrame()


def calculate_indicators(df):
    """
    Calculate technical indicators.
    """
    if df.empty:
        return df

    # EMA 200
    df["ema200"] = ta.EMA(df, timeperiod=200)

    # ADX 14
    df["adx"] = ta.ADX(df, timeperiod=14)

    # ATR 14 (Volatility)
    df["atr"] = ta.ATR(df, timeperiod=14)

    return df


def determine_regime(df):
    """
    Determine the market regime based on the latest candle.
    """
    if df.empty or len(df) < 200:
        logger.warning("Not enough data to determine regime.")
        return "Unknown", "BollingerRSI"

    last_row = df.iloc[-1]
    close = last_row["close"]
    ema200 = last_row["ema200"]
    adx = last_row["adx"]
    # vol_ratio = last_row['atr'] / close # Percentage volatility

    logger.info(f"Analysis - Price: {close}, EMA200: {ema200}, ADX: {adx}")

    # Logic
    # Bull Market: Price > EMA200, ADX > 25
    if close > ema200 and adx > 25:
        return "Bull Market", "MomentumVolumeTrend"

    # Sideways/Choppy: ADX < 20
    elif adx < 20:
        return "Sideways/Choppy", "BollingerRSI"

    # Volatile/Crashing: Price < EMA200 (Simplified)
    # The prompt says "VIX spike, Price < EMA200". We treat Price < EMA200 as the main trigger.
    elif close < ema200:
        return "Volatile/Crashing", "VolatilityBreakout"

    # Default/Gray Area
    else:
        return "Neutral/Uncertain", "BollingerRSI"


def load_config_robust(path):
    """
    Load JSON config, handling comments if possible.
    """
    try:
        import rapidjson

        with path.open() as f:
            return rapidjson.load(
                f, parse_mode=rapidjson.PM_COMMENTS | rapidjson.PM_TRAILING_COMMAS
            )
    except ImportError:
        # Fallback to standard json
        with path.open() as f:
            content = f.read()

        # We try to load as standard JSON.
        # If the file contains comments, this will fail unless we are very careful.
        # Given we can't easily parse comments without a proper parser, we stick to standard JSON
        # but warn if rapidjson is missing.
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            logger.warning(
                "Failed to load config with standard JSON parser. "
                "If your config contains comments, please install 'python-rapidjson'."
            )
            raise


def update_config(strategy_name):
    """
    Update the strategy in config_production.json.
    """
    root = get_project_root()
    config_path = root / "user_data" / "configs" / "config_production.json"

    if not config_path.exists():
        logger.error(f"Config file not found at {config_path}")
        return False

    try:
        config = load_config_robust(config_path)

        current_strategy = config.get("strategy")
        if current_strategy == strategy_name:
            logger.info(f"Strategy is already set to {strategy_name}. No change needed.")
            return True

        config["strategy"] = strategy_name

        with config_path.open("w") as f:
            json.dump(config, f, indent=4)

        logger.info(f"Updated config strategy to {strategy_name}")
        return True
    except Exception as e:
        logger.error(f"Failed to update config: {e}")
        return False


def log_regime(regime, strategy):
    """
    Log the decision to regime_log.md.
    """
    root = get_project_root()
    log_path = root / "regime_log.md"

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")  # noqa: UP017
    log_entry = f"| {timestamp} | {regime} | {strategy} |\n"

    # Create header if file doesn't exist
    if not log_path.exists():
        with log_path.open("w") as f:
            f.write("| Timestamp | Regime | Activated Strategy |\n")
            f.write("|---|---|---|\n")

    with log_path.open("a") as f:
        f.write(log_entry)

    logger.info(f"Logged regime change: {regime} -> {strategy}")


def main():
    logger.info("Starting Regime Switcher...")

    # 1. Fetch Data
    df = fetch_market_data()
    if df.empty:
        logger.error("No data fetched. Exiting.")
        sys.exit(1)

    # 2. Calculate Indicators
    df = calculate_indicators(df)

    # 3. Determine Regime
    regime, strategy = determine_regime(df)
    logger.info(f"Detected Regime: {regime}. Strategy: {strategy}")

    # 4. Update Config
    if update_config(strategy):
        # 5. Log
        log_regime(regime, strategy)
    else:
        logger.error("Failed to update config.")
        sys.exit(1)

    logger.info("Regime Switcher completed successfully.")


if __name__ == "__main__":
    main()
