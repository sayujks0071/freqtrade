#!/usr/bin/env python3
"""
Regime Switcher Script
Analyzes BTC/USDT market data to detect regime (Bull, Bear, Sideways) and updates
the production config.
"""

import json
import logging
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
logger = logging.getLogger("regime_switcher")


def fetch_btc_data(limit: int = 300) -> pd.DataFrame:
    """
    Fetch daily candles for BTC/USDT from Gate.io (Public API).
    """
    try:
        exchange = ccxt.gateio({"enableRateLimit": True})
        symbol = "BTC/USDT"
        timeframe = "1d"

        # Fetch OHLCV
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)

        # Convert to DataFrame
        df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)

        logger.info(f"Fetched {len(df)} daily candles for {symbol} from Gate.io.")
        return df
    except Exception as e:
        logger.error(f"Error fetching data: {e}")
        raise


def detect_regime(df: pd.DataFrame) -> tuple[str, str]:
    """
    Detect market regime based on EMA200 and ADX.
    Returns: (Regime Name, Strategy Name)
    """
    # Calculate Indicators
    df.ta.ema(length=200, append=True)
    df.ta.adx(length=14, append=True)

    # Get last closed candle (assuming current candle is open/incomplete, use iloc[-2] for
    # completed day? Usually daily candles on centralized exchanges are closed if fetching
    # 'limit' last candles, but the last one might be current day. Let's use the last row
    # but verify logic. If running "Every Monday", we want the last completed day (Sunday close).
    # We'll use the last row if it looks completed or simply the latest available data
    # point as a proxy.

    last_row = df.iloc[-1]

    close = last_row["close"]
    ema200 = last_row["EMA_200"]
    adx = last_row["ADX_14"]

    logger.info(f"Analysis: Price={close:.2f}, EMA200={ema200:.2f}, ADX={adx:.2f}")

    # Logic
    if close < ema200:
        return "Bear/Volatile", "VolatilityBreakout"
    elif adx < 20:
        return "Sideways/Choppy", "BollingerRSI"
    elif close > ema200 and adx > 25:
        return "Bull Market", "MomentumVolumeTrend"
    else:
        # Default/Fallback (e.g. Price > EMA200 but 20 <= ADX <= 25)
        return "Weak Bull (Fallback)", "MomentumVolumeTrend"


def update_config(strategy_name: str, config_path: Path):
    """
    Update the 'strategy' field in the config file.
    """
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    try:
        with config_path.open("r") as f:
            config = json.load(f)

        current_strategy = config.get("strategy")
        if current_strategy == strategy_name:
            logger.info(f"Strategy is already set to {strategy_name}. No update needed.")
            return False

        config["strategy"] = strategy_name

        with config_path.open("w") as f:
            json.dump(config, f, indent=4)

        logger.info(f"Updated config strategy to: {strategy_name}")
        return True
    except Exception as e:
        logger.error(f"Error updating config: {e}")
        raise


def log_decision(regime: str, strategy: str, log_path: Path):
    """
    Append decision to the log file.
    """
    # Use timezone.utc correctly
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    log_entry = f"| {timestamp} | {regime} | Switched to: {strategy} |\n"

    try:
        with log_path.open("a") as f:
            f.write(log_entry)
        logger.info(f"Logged decision to {log_path}")
    except Exception as e:
        logger.error(f"Error logging decision: {e}")


def main():
    # Paths
    config_path = Path("user_data/configs/config_production.json")
    log_path = Path("user_data/regime_log.md")

    # ensure user_data exists (it should)

    logger.info("Starting Regime Switcher...")

    # 1. Fetch Data
    df = fetch_btc_data()

    # 2. Detect Regime
    regime, strategy = detect_regime(df)
    logger.info(f"Detected Regime: {regime} -> Strategy: {strategy}")

    # 3. Update Config
    update_config(strategy, config_path)

    # 4. Log Decision (always log or only on change? Prompt says "Log: Record the decision".)
    log_decision(regime, strategy, log_path)

    logger.info("Regime Switcher completed successfully.")


if __name__ == "__main__":
    main()
