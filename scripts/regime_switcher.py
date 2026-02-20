#!/usr/bin/env python3
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
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

CONFIG_PATH = Path("user_data/configs/config.delta.live.json")
PRODUCTION_CONFIG_PATH = Path("user_data/config_production.json")
LOG_FILE = Path("regime_log.md")


def fetch_btc_data():
    """Fetches daily OHLCV for BTC/USDT from Gate.io (fallback from Binance)."""
    try:
        try:
            exchange = ccxt.binance()
            ohlcv = exchange.fetch_ohlcv("BTC/USDT", timeframe="1d", limit=300)
        except Exception:
            logger.warning("Binance failed, trying Gate.io")
            exchange = ccxt.gateio()
            ohlcv = exchange.fetch_ohlcv("BTC/USDT", timeframe="1d", limit=300)

        df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        return df
    except Exception as e:
        logger.error(f"Error fetching data: {e}")
        sys.exit(1)


def calculate_indicators(df):
    """Calculates EMA200, ADX(14), ATR(14)."""
    # Ensure sufficient data
    if len(df) < 200:
        logger.error("Insufficient data for EMA200")
        sys.exit(1)

    # Calculate indicators using pandas_ta
    df.ta.ema(length=200, append=True)
    df.ta.adx(length=14, append=True)
    df.ta.atr(length=14, append=True)

    return df


def detect_regime(df):
    """
    Detects market regime based on the latest candle.

    Rules:
    - Bull: Close > EMA200 AND ADX > 25 -> MomentumVolumeTrend
    - Sideways: ADX < 20 -> BollingerRSI
    - Volatile/Bear: Close < EMA200 OR (ATR > Threshold) -> VolatilityBreakout
    """
    latest = df.iloc[-1]

    close = latest["close"]
    ema200 = latest["EMA_200"]
    adx = latest["ADX_14"]
    atr = latest["ATRr_14"]

    # ATR threshold for volatility?
    # "Volatile/Crashing: VIX spike".
    # I'll use ATR relative to price. If ATR/Price > 0.05 (5% daily move), that's high.
    volatility_ratio = atr / close

    regime = "Unknown"
    strategy = "MomentumVolumeTrend"  # Default
    unidirectional = True

    if close > ema200 and adx > 25:
        regime = "Bull"
        strategy = "MomentumVolumeTrend"
        unidirectional = True
    elif adx < 20:
        regime = "Sideways"
        strategy = "BollingerRSI"
        unidirectional = True  # Usually safer to be long-only or neutral.
    elif close < ema200 or volatility_ratio > 0.05:
        regime = "Volatile/Bear"
        strategy = "VolatilityBreakout"
        unidirectional = False  # Enable shorts
    else:
        # Fallback
        if close > ema200:
            # Weak Bull
            regime = "Weak Bull"
            strategy = "MomentumVolumeTrend"
            if adx < 25:
                strategy = "BollingerRSI"
        else:
            # Weak Bear
            regime = "Weak Bear"
            strategy = "VolatilityBreakout"
            unidirectional = False

    logger.info(
        f"Detected Regime: {regime} "
        f"(Close={close:.2f}, EMA200={ema200:.2f}, ADX={adx:.2f}, "
        f"ATR/Price={volatility_ratio:.4f})"
    )
    return regime, strategy, unidirectional


def update_config(strategy_name, unidirectional):
    """Updates the production config."""

    config = {}

    # 1. Try to load existing production config
    if PRODUCTION_CONFIG_PATH.exists():
        try:
            with PRODUCTION_CONFIG_PATH.open("r") as f:
                config = json.load(f)
            logger.info(f"Loaded existing config from {PRODUCTION_CONFIG_PATH}")
        except json.JSONDecodeError:
            logger.error(f"Error reading {PRODUCTION_CONFIG_PATH}, skipping.")

    # 2. If config is still empty (or missing), try template
    if not config:
        if CONFIG_PATH.exists():
            try:
                with CONFIG_PATH.open("r") as f:
                    config = json.load(f)
                logger.info(f"Loaded template config from {CONFIG_PATH}")
            except json.JSONDecodeError:
                logger.error(f"Error reading template {CONFIG_PATH}")
        else:
            logger.warning(f"Template config {CONFIG_PATH} not found.")

    # 3. If still empty, abort to avoid creating a broken config
    if not config:
        logger.error("No valid configuration found. Aborting update.")
        sys.exit(1)

    # Update strategy
    config["strategy"] = strategy_name
    config["unidirectional_only"] = unidirectional

    # Ensure directory exists
    PRODUCTION_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Save to production config
    with PRODUCTION_CONFIG_PATH.open("w") as f:
        json.dump(config, f, indent=4)

    logger.info(
        f"Updated {PRODUCTION_CONFIG_PATH} with strategy={strategy_name}, "
        f"unidirectional_only={unidirectional}"
    )


def log_decision(regime, strategy):
    """Logs the decision to regime_log.md."""
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    message = f"| {timestamp} | {regime} | {strategy} |"

    if not LOG_FILE.exists():
        with LOG_FILE.open("w") as f:
            f.write("| Timestamp | Regime | Strategy |\n")
            f.write("|---|---|---|\n")

    with LOG_FILE.open("a") as f:
        f.write(message + "\n")

    logger.info(f"Logged decision to {LOG_FILE}")


def main():
    logger.info("Starting Regime Detection...")

    # 1. Fetch Data
    df = fetch_btc_data()

    # 2. Calculate Indicators
    df = calculate_indicators(df)

    # 3. Detect Regime
    regime, strategy, unidirectional = detect_regime(df)

    # 4. Update Config
    update_config(strategy, unidirectional)

    # 5. Log
    log_decision(regime, strategy)

    logger.info("Regime detection completed.")


if __name__ == "__main__":
    main()
