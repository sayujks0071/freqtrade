#!/usr/bin/env python3
"""
Regime Switcher Script
Analyzes BTC/USDT market conditions and updates the active strategy.
"""

import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import talib.abstract as ta


# Add root to path to allow imports from freqtrade
sys.path.append(str(Path(__file__).parent.parent))

from freqtrade.configuration import Configuration  # noqa: E402, RUF100
from freqtrade.data.history import load_pair_history  # noqa: E402, RUF100
from freqtrade.enums import CandleType, TradingMode  # noqa: E402, RUF100


# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("RegimeSwitcher")

# Constants
USER_DATA_DIR = Path("user_data")
CONFIG_PATH = USER_DATA_DIR / "configs/config_production.json"
REGIME_LOG_PATH = Path("regime_log.md")
PAIR = "BTC/USDT"
TIMEFRAME = "1h"


def get_market_regime(dataframe: pd.DataFrame):
    """
    Determine market regime based on indicators.
    """
    # Calculate indicators
    dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)  # type: ignore
    dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)  # type: ignore

    # Get last closed candle (assuming data includes up to latest)
    last_candle = dataframe.iloc[-1]

    price = last_candle["close"]
    ema200 = last_candle["ema200"]
    adx = last_candle["adx"]

    logger.info(f"Analysis - Price: {price:.2f}, EMA200: {ema200:.2f}, ADX: {adx:.2f}")

    # Logic
    # Bull Market: Price > EMA200, ADX > 25
    if price > ema200 and adx > 25:
        return "Bull", "MomentumVolumeTrend"

    # Sideways/Choppy: ADX < 20
    elif adx < 20:
        return "Sideways", "BollingerRSI"

    # Volatile/Crashing: Price < EMA200
    elif price < ema200:
        return "Volatile", "VolatilityBreakout"

    else:
        # Default / Transition
        return "Transition (Bullish)", "MomentumVolumeTrend"


def update_config(strategy_name: str):
    """
    Update the config file with the selected strategy.
    """
    if not CONFIG_PATH.exists():
        logger.error(f"Config file not found: {CONFIG_PATH}")
        return False

    try:
        with CONFIG_PATH.open("r") as f:
            config = json.load(f)

        current_strategy = config.get("strategy")
        if current_strategy == strategy_name:
            logger.info(f"Strategy is already set to {strategy_name}. No change needed.")
            return False

        config["strategy"] = strategy_name

        with CONFIG_PATH.open("w") as f:
            json.dump(config, f, indent=4)

        logger.info(f"Updated config with strategy: {strategy_name}")
        return True

    except Exception as e:
        logger.error(f"Failed to update config: {e}")
        return False


def log_decision(regime: str, strategy: str):
    """
    Log the decision to regime_log.md.
    """
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    message = f"| {timestamp} | {regime} | {strategy} |"

    if not REGIME_LOG_PATH.exists():
        with REGIME_LOG_PATH.open("w") as f:
            f.write("| Timestamp | Regime | Strategy |\n")
            f.write("| --- | --- | --- |\n")

    with REGIME_LOG_PATH.open("a") as f:
        f.write(message + "\n")


def main():
    # 1. Load Data
    # Convert Path to string for Configuration.from_files
    config = Configuration.from_files([str(CONFIG_PATH)])

    # Determine datadir and candle_type
    datadir = config["user_data_dir"] / "data" / config["exchange"]["name"]
    trading_mode = config.get("trading_mode", TradingMode.SPOT)
    candle_type = CandleType.FUTURES if trading_mode == TradingMode.FUTURES else CandleType.SPOT

    logger.info(f"Loading data from {datadir} for {PAIR} {TIMEFRAME} ({candle_type})")

    try:
        data = load_pair_history(
            datadir=datadir, timeframe=TIMEFRAME, pair=PAIR, candle_type=candle_type
        )
    except Exception as e:
        logger.error(f"Error loading data: {e}")
        sys.exit(1)

    if data.empty:
        logger.error("No data found for BTC/USDT. Please run `freqtrade download-data`.")
        sys.exit(1)

    # 2. Analyze
    regime, strategy = get_market_regime(data)
    logger.info(f"Detected Regime: {regime} -> Activating {strategy}")

    # 3. Update Config
    changed = update_config(strategy)

    # 4. Log
    if changed:
        log_decision(regime, strategy)
        print(f"Switched to {regime} Mode: Activated {strategy}")
    else:
        print(f"Regime {regime} unchanged. Strategy {strategy} remains active.")


if __name__ == "__main__":
    main()
