#!/usr/bin/env python3
"""
Regime Switcher Script
Analyzes BTC/USDT market data and updates the trading strategy in config_production.json.
"""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import ccxt
import pandas as pd
import pandas_ta  # noqa: F401


# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("RegimeSwitcher")

CONFIG_PATH = Path("user_data/configs/config_production.json")
LOG_PATH = Path("regime_log.md")


def fetch_data(symbol="BTC/USDT", timeframe="1d", limit=365):
    """Fetch OHLCV data from Kraken (Public API) as fallback."""
    logger.info(f"Fetching {symbol} data ({timeframe})...")
    try:
        # Try Kraken (uses XBT/USD usually but CCXT handles mapping, if not we try alternative)
        exchange = ccxt.kraken()
        # Kraken might need specific symbol mapping if BTC/USDT not available, usually XBT/USD
        # Let's try to load markets first or just try BTC/USDT
        # If BTC/USDT fails, try BTC/USD
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        except Exception:
            ohlcv = exchange.fetch_ohlcv("BTC/USD", timeframe, limit=limit)

        df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        return df
    except Exception as e:
        logger.error(f"Error fetching data from Kraken: {e}")
        return pd.DataFrame()


def analyze_market(df):
    """Determine market regime based on indicators."""
    if df.empty:
        return None

    # Calculate Indicators
    # EMA 200
    df.ta.ema(length=200, append=True)
    # ADX 14
    df.ta.adx(length=14, append=True)

    # Get latest completed candle (second to last, as last is current/incomplete)
    # But usually daily candles from API for 'today' might be incomplete or completed 'yesterday'.
    # If using 1d, fetch_ohlcv usually returns up to latest close.
    # We will look at the last row.

    latest = df.iloc[-1]

    # Ensure columns exist (pandas_ta naming conventions)
    # EMA_200, ADX_14
    # Note: ADX usually returns ADX_14, DMP_14, DMN_14. We need ADX_14.

    close = latest["close"]
    ema200 = latest.get("EMA_200")
    adx = latest.get("ADX_14")

    if ema200 is None or adx is None:
        logger.warning("Not enough data to calculate indicators (NaN).")
        # Check previous row if current is NaN
        latest = df.iloc[-2]
        close = latest["close"]
        ema200 = latest.get("EMA_200")
        adx = latest.get("ADX_14")
        if ema200 is None:
            logger.error("Indicators are still NaN.")
            return None

    logger.info(f"Market Data: Price={close:.2f}, EMA200={ema200:.2f}, ADX={adx:.2f}")

    # Logic
    regime = "Uncertain"
    strategy = "BollingerRSI"  # Default to Sideways/Safe

    # Bull Market
    if close > ema200 and adx > 25:
        regime = "Bull"
        strategy = "MomentumVolumeTrend"

    # Sideways/Choppy
    elif adx < 20:
        regime = "Sideways"
        strategy = "BollingerRSI"

    # Volatile/Bear (Price < EMA200)
    elif close < ema200:
        regime = "Bear/Volatile"
        strategy = "VolatilityBreakout"

    # If ADX between 20 and 25 and Price > EMA200?
    # It's a weak bull or transition.
    # Defaulting to BollingerRSI (Sideways) seems safer or stay with previous.
    # For now, explicit logic:
    else:
        regime = "Transition (Weak Bull)"
        strategy = "BollingerRSI"

    return regime, strategy, latest


def update_config(strategy_name):
    """Update strategy in config_production.json."""
    if not CONFIG_PATH.exists():
        logger.error(f"Config file not found: {CONFIG_PATH}")
        # If it doesn't exist, we can't update it. But in our plan we create it.
        return False

    try:
        with CONFIG_PATH.open() as f:
            config = json.load(f)

        current_strategy = config.get("strategy")

        if current_strategy == strategy_name:
            logger.info(f"Strategy is already {strategy_name}. No update needed.")
            return False

        config["strategy"] = strategy_name

        with CONFIG_PATH.open("w") as f:
            json.dump(config, f, indent=4)

        logger.info(f"Updated config with strategy: {strategy_name}")
        return True
    except Exception as e:
        logger.error(f"Error updating config: {e}")
        return False


def log_decision(regime, strategy, market_data):
    """Log decision to regime_log.md."""
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

    close = market_data["close"]
    ema200 = market_data.get("EMA_200", 0)
    adx = market_data.get("ADX_14", 0)

    message = (
        f"## {timestamp}\n"
        f"- **Regime Detected:** {regime}\n"
        f"- **Strategy Activated:** `{strategy}`\n"
        f"- **Market Data (BTC/USDT):** Price={close:.2f}, EMA200={ema200:.2f}, ADX={adx:.2f}\n"
        f"---\n"
    )

    try:
        with LOG_PATH.open("a") as f:
            f.write(message)
        logger.info(f"Logged decision: {regime} -> {strategy}")
    except Exception as e:
        logger.error(f"Error writing to log: {e}")


def main():
    logger.info("Starting Regime Switcher...")

    df = fetch_data()
    if df.empty:
        logger.error("No data fetched. Exiting.")
        return

    result = analyze_market(df)
    if not result:
        logger.error("Analysis failed.")
        return

    regime, strategy, market_data = result

    update_config(strategy)
    log_decision(regime, strategy, market_data)

    logger.info("Regime Switcher completed.")


if __name__ == "__main__":
    main()
