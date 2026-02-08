#!/usr/bin/env python3
import sys
import json
import logging
from pathlib import Path
from datetime import datetime, timezone

import ccxt
import pandas as pd
import pandas_ta as ta

# Constants
PAIR = "BTC/USDT"
TIMEFRAME = "1d"
LIMIT = 300
CONFIG_PATH = Path("user_data/configs/config_production.json")
LOG_FILE = Path("regime_log.md")

# Strategies
STRATEGY_BULL = "MomentumVolumeTrend"
STRATEGY_SIDEWAYS = "BollingerRSI"
STRATEGY_BEAR = "VolatilityBreakout"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def get_market_data():
    try:
        exchange = ccxt.binance()
        logger.info(f"Fetching {TIMEFRAME} data for {PAIR} from Binance...")
        ohlcv = exchange.fetch_ohlcv(PAIR, timeframe=TIMEFRAME, limit=LIMIT)
    except Exception as e:
        logger.warning(f"Binance failed ({e}), trying KuCoin...")
        exchange = ccxt.kucoin()
        logger.info(f"Fetching {TIMEFRAME} data for {PAIR} from KuCoin...")
        ohlcv = exchange.fetch_ohlcv(PAIR, timeframe=TIMEFRAME, limit=LIMIT)

    df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df


def analyze_regime(df):
    # Calculate Indicators
    # EMA 200
    df.ta.ema(length=200, append=True)
    # ADX 14
    df.ta.adx(length=14, append=True)

    # Get last closed candle (index -2)
    last_candle = df.iloc[-2]
    close = last_candle["close"]
    ema200 = last_candle["EMA_200"]
    adx = last_candle["ADX_14"]

    logger.info(
        f"Analysis on {last_candle['timestamp']}: Close={close}, EMA200={ema200}, ADX={adx}"
    )

    regime = "Unknown"
    strategy = STRATEGY_BEAR  # Default fallback

    # Logic based on prompt:
    # 1. Bull: Price > EMA200, ADX > 25
    # 2. Sideways: ADX < 20
    # 3. Volatile/Bear: (Price < EMA200) -> VolatilityBreakout

    if close > ema200 and adx > 25:
        regime = "Bull Market"
        strategy = STRATEGY_BULL
    elif adx < 20:
        regime = "Sideways/Choppy"
        strategy = STRATEGY_SIDEWAYS
    else:
        # Falls here if (Close < EMA200) OR (Close > EMA200 but ADX between 20-25)
        # If Price < EMA200, it's Bear.
        # If Price > EMA200 but ADX < 25 (but > 20), it's neither Bull nor Sideways.
        # Maybe weak trend?
        # I'll default to VolatilityBreakout (Bear/Volatile) if Price < EMA200.
        # If Price > EMA200 and ADX in [20, 25], let's default to Sideways (BollingerRSI) as it's low trend.

        if close < ema200:
            regime = "Volatile/Bear"
            strategy = STRATEGY_BEAR
        else:
            # Weak Bull / Range
            regime = "Weak Bull/Range (ADX 20-25)"
            strategy = STRATEGY_SIDEWAYS

    return regime, strategy


def update_config(strategy_name):
    if not CONFIG_PATH.exists():
        logger.error(f"Config file not found: {CONFIG_PATH}")
        # In this specific task flow, we might be creating it later or expect it.
        # I'll return False but log error.
        return False

    try:
        with open(CONFIG_PATH, "r") as f:
            config = json.load(f)

        current_strategy = config.get("strategy")
        if current_strategy == strategy_name:
            logger.info(f"Strategy is already {strategy_name}. No update needed.")
            return False

        config["strategy"] = strategy_name

        with open(CONFIG_PATH, "w") as f:
            json.dump(config, f, indent=4)

        logger.info(f"Updated config with strategy: {strategy_name}")
        return True
    except Exception as e:
        logger.error(f"Failed to update config: {e}")
        return False


def log_decision(regime, strategy_name):
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    message = (
        f"- **{timestamp}**: Regime detected: `{regime}`. Action: Switched to `{strategy_name}`.\n"
    )

    # Ensure file exists or create it
    if not LOG_FILE.exists():
        with open(LOG_FILE, "w") as f:
            f.write("# Regime Switcher Log\n\n")

    with open(LOG_FILE, "a") as f:
        f.write(message)
    logger.info("Logged decision to regime_log.md")


def main():
    try:
        df = get_market_data()
        regime, strategy = analyze_regime(df)
        logger.info(f"Determined Regime: {regime} -> Strategy: {strategy}")

        update_config(strategy)
        log_decision(regime, strategy)

    except Exception as e:
        logger.error(f"Error in regime switcher: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
