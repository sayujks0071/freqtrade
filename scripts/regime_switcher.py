#!/usr/bin/env python3
"""
Regime Switcher Script
Analyzes BTC/USDT to determine market regime and switches strategy in config_production.json.
"""

import json
import logging
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path


# Add project root to path to allow importing freqtrade
sys.path.append(str(Path(__file__).resolve().parent.parent))

import talib.abstract as ta  # noqa: E402, RUF100


# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("RegimeSwitcher")

# Constants
# Using Gate.io as Binance is restricted
PAIR = "BTC/USDT"
TIMEFRAME = "1d"
DAYS_TO_DOWNLOAD = 300
USER_DATA_DIR = Path("user_data")
CONFIG_PATH = USER_DATA_DIR / "configs/config_production.json"
REGIME_LOG_PATH = Path("regime_log.md")


def analyze_regime(dataframe):
    """Analyze indicators to determine regime."""
    # Indicators
    dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
    dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)

    last_candle = dataframe.iloc[-1]

    price = last_candle["close"]
    ema200 = last_candle["ema200"]
    adx = last_candle["adx"]
    date = last_candle["date"]

    logger.info(f"Analysis Date: {date}, Price: {price}, EMA200: {ema200}, ADX: {adx}")

    regime = "Unknown"
    strategy = "BollingerRSI"  # Default

    # Logic
    # Volatile/Crashing: Price < EMA200
    if price < ema200:
        regime = "Volatile/Crashing"
        strategy = "VolatilityBreakout"
    # Bull Market: Price > EMA200, ADX > 25
    elif price > ema200 and adx > 25:
        regime = "Bull Market"
        strategy = "MomentumVolumeTrend"
    # Sideways/Choppy: ADX < 20
    elif adx < 20:
        regime = "Sideways/Choppy"
        strategy = "BollingerRSI"
    else:
        # Fallback for Price > EMA200 but ADX between 20 and 25
        regime = "Weak Bull/Indecisive"
        strategy = "BollingerRSI"

    return regime, strategy, last_candle


def update_config(strategy_name):
    """Update the strategy in config_production.json."""
    if not CONFIG_PATH.exists():
        logger.error(f"Config file not found at {CONFIG_PATH}")
        return False

    try:
        with CONFIG_PATH.open("r") as f:
            config = json.load(f)

        current_strategy = config.get("strategy")
        if current_strategy == strategy_name:
            logger.info(f"Strategy is already {strategy_name}. No change needed.")
            return False

        config["strategy"] = strategy_name

        with CONFIG_PATH.open("w") as f:
            json.dump(config, f, indent=4)

        logger.info(f"Updated config strategy to {strategy_name}")
        return True
    except Exception as e:
        logger.error(f"Failed to update config: {e}")
        return False


def log_decision(regime, strategy, candle):
    """Log the decision to regime_log.md."""
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

    log_entry = (
        f"| {timestamp} | {candle['date']} | {candle['close']:.2f} | "
        f"{candle['ema200']:.2f} | {candle['adx']:.2f} | {regime} | {strategy} |\n"
    )

    if not REGIME_LOG_PATH.exists():
        with REGIME_LOG_PATH.open("w") as f:
            f.write("| Timestamp | Candle Date | Price | EMA200 | ADX | Regime | Strategy |\n")
            f.write("|---|---|---|---|---|---|---|\n")

    with REGIME_LOG_PATH.open("a") as f:
        f.write(log_entry)

    logger.info(f"Logged decision: {regime} -> {strategy}")


def main():
    # 1. Download Data (Gate.io Spot for analysis due to Binance restriction)
    logger.info(f"Downloading data for {PAIR} from Gate.io...")
    cmd = [
        sys.executable,
        "-m",
        "freqtrade",
        "download-data",
        "--exchange",
        "gate",
        "--pairs",
        PAIR,
        "--timeframe",
        TIMEFRAME,
        "--days",
        str(DAYS_TO_DOWNLOAD),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode() if e.stderr else str(e)
        logger.warning(
            f"Failed to download Gate.io data: {error_msg}. "
            "Trying to proceed if data exists..."
        )

    # 2. Load Data
    try:
        from freqtrade.data.history import load_pair_history
        from freqtrade.enums import CandleType

        # We explicitly look in gate directory
        data = load_pair_history(
            datadir=USER_DATA_DIR / "data/gate",
            timeframe=TIMEFRAME,
            pair=PAIR,
            candle_type=CandleType.SPOT,
        )
    except Exception as e:
        logger.error(f"CRITICAL: Could not load data. {e}")
        sys.exit(1)

    if data.empty:
        logger.error("Dataframe is empty.")
        sys.exit(1)

    # 3. Analyze
    regime, strategy, last_candle = analyze_regime(data)
    logger.info(f"Detected Regime: {regime}. Activating: {strategy}")

    # 4. Update Config
    update_config(strategy)

    # 5. Log
    log_decision(regime, strategy, last_candle)


if __name__ == "__main__":
    main()
