#!/usr/bin/env python3
"""
Regime Switcher Script
Analyzes BTC/USDT market regime and updates strategy configuration.
"""

import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path


# Ensure dependencies are available
try:
    import ccxt
    import pandas as pd
    import pandas_ta as ta  # noqa: F401
except ImportError as e:
    print(f"Error importing dependencies: {e}")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("RegimeSwitcher")

CONFIG_PATH = Path("user_data/configs/config_production.json")
LOG_FILE = Path("regime_log.md")

STRATEGIES = {
    "Bull": "MomentumVolumeTrend",
    "Sideways": "BollingerRSI",
    "Volatile": "VolatilityBreakout",
}


def fetch_data(symbol: str = "BTC/USDT", timeframe: str = "1d", limit: int = 300) -> pd.DataFrame:
    exchanges = ["delta", "kraken", "gateio"]

    for exchange_id in exchanges:
        try:
            logger.info(f"Attempting to fetch data from {exchange_id}...")
            exchange_class = getattr(ccxt, exchange_id)
            exchange = exchange_class()

            # Fetch OHLCV
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            if not ohlcv:
                continue

            df = pd.DataFrame(
                ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"]
            )
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")

            logger.info(f"Successfully fetched {len(df)} candles from {exchange_id}")
            return df

        except Exception as e:
            logger.warning(f"Failed to fetch from {exchange_id}: {e}")
            continue

    raise RuntimeError("Failed to fetch data from all available exchanges.")


def analyze_market(df: pd.DataFrame) -> dict:
    # Calculate indicators
    df.ta.ema(length=200, append=True)
    df.ta.adx(length=14, append=True)

    # Use the second to last candle to ensure it's closed
    last_row_index = -2
    if len(df) < 201:
        # Not enough data for EMA200
        logger.warning("Not enough data for EMA200. Defaulting to Sideways.")
        return {
            "regime": "Sideways",
            "strategy": STRATEGIES["Sideways"],
            "reason": "Insufficient data for EMA200",
            "data": {
                "close": df["close"].iloc[-1],
                "ema_200": 0.0,
                "adx": 0.0,
                "timestamp": df["timestamp"].iloc[-1].isoformat(),
            },
        }

    close = df["close"].iloc[last_row_index]
    ema_200 = df["EMA_200"].iloc[last_row_index]
    adx = df["ADX_14"].iloc[last_row_index]

    # Regime Logic
    regime = "Sideways"  # Default
    reason = []

    if close > ema_200 and adx > 25:
        regime = "Bull"
        reason.append(f"Price ({close:.2f}) > EMA200 ({ema_200:.2f}) and ADX ({adx:.2f}) > 25")
    elif adx < 20:
        regime = "Sideways"
        reason.append(f"ADX ({adx:.2f}) < 20")
    elif close < ema_200:
        regime = "Volatile"
        reason.append(f"Price ({close:.2f}) < EMA200 ({ema_200:.2f}) (Bear/Crash)")
    else:
        regime = "Sideways"
        reason.append(f"Fallback: ADX {adx:.2f}, Price {close:.2f} vs EMA {ema_200:.2f}")

    return {
        "regime": regime,
        "strategy": STRATEGIES[regime],
        "reason": "; ".join(reason),
        "data": {
            "close": close,
            "ema_200": ema_200,
            "adx": adx,
            "timestamp": df["timestamp"].iloc[last_row_index].isoformat(),
        },
    }


def update_config(strategy_name: str):
    if not CONFIG_PATH.exists():
        logger.error(f"Config file not found: {CONFIG_PATH}")
        return

    try:
        with CONFIG_PATH.open() as f:
            config = json.load(f)

        current_strategy = config.get("strategy")
        if current_strategy == strategy_name:
            logger.info(f"Strategy is already set to {strategy_name}. No change needed.")
            return

        config["strategy"] = strategy_name

        with CONFIG_PATH.open("w") as f:
            json.dump(config, f, indent=4)

        logger.info(f"Updated config with strategy: {strategy_name}")

    except Exception as e:
        logger.error(f"Failed to update config: {e}")


def log_decision(analysis: dict):
    timestamp = datetime.now(UTC).isoformat()
    entry = (
        f"## {timestamp}\n"
        f"- **Regime:** {analysis['regime']}\n"
        f"- **Strategy:** {analysis['strategy']}\n"
        f"- **Reason:** {analysis['reason']}\n"
        f"- **Data:** Close={analysis['data']['close']:.2f}, "
        f"EMA200={analysis['data']['ema_200']:.2f}, "
        f"ADX={analysis['data']['adx']:.2f}\n"
        f"---\n"
    )

    try:
        with LOG_FILE.open("a") as f:
            f.write(entry)
        logger.info(f"Logged decision to {LOG_FILE}")
    except Exception as e:
        logger.error(f"Failed to log decision: {e}")


def main():
    logger.info("Starting Regime Switcher...")
    try:
        df = fetch_data()
        analysis = analyze_market(df)
        logger.info(f"Market Analysis: {analysis}")

        update_config(analysis["strategy"])
        log_decision(analysis)

        logger.info("Regime Switcher completed successfully.")

    except Exception as e:
        logger.error(f"Regime Switcher failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
