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
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("RegimeSwitcher")

USER_DATA_DIR = Path("user_data")
CONFIG_FILE = USER_DATA_DIR / "configs/config_production.json"
REGIME_LOG_FILE = USER_DATA_DIR / "regime_log.md"

def fetch_data(symbol="BTC/USDT", timeframe="1d", limit=300):
    """Fetch OHLCV data from Gate.io"""
    exchange = ccxt.gateio()
    try:
        # Gate.io might have limits or specific symbol format?
        # CCXT handles normalization usually.
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        logger.error(f"Error fetching data from Gate.io: {e}")
        return pd.DataFrame()

def analyze_market(df):
    """Analyze market regime"""
    if df.empty:
        return None

    # Calculate Indicators
    # Ensure we have enough data
    if len(df) < 200:
        logger.warning(f"Not enough data for EMA200. Got {len(df)} rows.")
        return None

    df.ta.ema(length=200, append=True)
    df.ta.adx(length=14, append=True)

    # Get last complete candle (second to last)
    # Assuming the last row is the current forming candle
    if len(df) < 2:
        return None

    last_candle = df.iloc[-2]

    close = last_candle['close']
    ema200 = last_candle['EMA_200']
    adx = last_candle['ADX_14']

    if pd.isna(ema200) or pd.isna(adx):
        logger.warning("Indicators are NaN. Need more history.")
        return None

    regime = "Unknown"
    strategy = "MomentumVolumeTrend" # Default

    # Logic
    # Bull Market: Price > EMA200, ADX > 25
    if close > ema200 and adx > 25:
        regime = "Bull Market"
        strategy = "MomentumVolumeTrend"
    # Sideways/Choppy: ADX < 20
    elif adx < 20:
        regime = "Sideways"
        strategy = "BollingerRSI"
    # Volatile/Crashing: Price < EMA200
    elif close < ema200:
        regime = "Bear/Volatile"
        strategy = "VolatilityBreakout"
    else:
        # Fallback
        regime = "Weak Trend/Transition"
        strategy = "BollingerRSI"

    return {
        "regime": regime,
        "strategy": strategy,
        "close": close,
        "ema200": ema200,
        "adx": adx,
        "timestamp": last_candle['timestamp']
    }

def update_config(strategy_name):
    """Update strategy in config_production.json"""
    if not CONFIG_FILE.exists():
        logger.error(f"Config file not found: {CONFIG_FILE}")
        return False

    try:
        with CONFIG_FILE.open('r') as f:
            config = json.load(f)

        current_strategy = config.get("strategy")

        # Ensure unidirectional_only is false to allow shorts if needed
        # (VolatilityBreakout uses shorts). We enforce this for all strategies.
        config_changed = False
        if config.get("unidirectional_only") is not False:
            config["unidirectional_only"] = False
            config_changed = True
            logger.info("Updated unidirectional_only to False")

        if current_strategy != strategy_name:
            config["strategy"] = strategy_name
            config_changed = True
            logger.info(f"Updated config strategy from {current_strategy} to {strategy_name}")

        if config_changed:
            with CONFIG_FILE.open('w') as f:
                json.dump(config, f, indent=4)
            return True
        else:
            logger.info(f"Strategy already set to {strategy_name}. No update needed.")
            return False

    except Exception as e:
        logger.error(f"Error updating config: {e}")
        return False

def log_decision(analysis_result, updated):
    """Log decision to regime_log.md"""
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

    log_entry = (
        f"## {timestamp}\n"
        f"- **Regime Detected:** {analysis_result['regime']}\n"
        f"- **Strategy Selected:** {analysis_result['strategy']}\n"
        f"- **Metrics:**\n"
        f"  - Close: {analysis_result['close']:.2f}\n"
        f"  - EMA200: {analysis_result['ema200']:.2f}\n"
        f"  - ADX: {analysis_result['adx']:.2f}\n"
        f"- **Action:** {'Switched Strategy' if updated else 'No Change'}\n"
        f"\n"
    )

    # Ensure directory exists
    REGIME_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    with REGIME_LOG_FILE.open('a') as f:
        f.write(log_entry)

    logger.info(f"Logged decision: {analysis_result['regime']} -> {analysis_result['strategy']}")

def main():
    logger.info("Starting Regime Switcher...")

    # 1. Fetch Data
    df = fetch_data()
    if df.empty or len(df) < 200:
        logger.error("Insufficient data fetched.")
        return

    # 2. Analyze
    analysis = analyze_market(df)
    if not analysis:
        logger.error("Analysis failed.")
        return

    logger.info(f"Analysis Result: {analysis}")

    # 3. Update Config
    updated = update_config(analysis['strategy'])

    # 4. Log
    log_decision(analysis, updated)

    logger.info("Regime Switcher completed.")

if __name__ == "__main__":
    main()
