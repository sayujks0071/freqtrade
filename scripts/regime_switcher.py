#!/usr/bin/env python3
"""
Regime Switcher
Analyzes market regime on BTC/USDT and updates the production config.
Regimes:
- Bull: Price > EMA200 & ADX > 25 -> MomentumVolumeTrend
- Sideways: ADX < 20 -> BollingerRSI
- Bear/Crash: Price < EMA200 -> VolatilityBreakout
"""

import json
import logging
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import ccxt
import pandas as pd
import talib.abstract as ta


# Configuration
CONFIG_PATH = Path("user_data/configs/config_production.json")
LOG_FILE = Path("regime_log.md")
PAIR = "BTC/USDT"
TIMEFRAME = "1d"
LIMIT = 365  # Need enough for EMA200

# Strategies
STRATEGY_BULL = "MomentumVolumeTrend"
STRATEGY_SIDEWAYS = "BollingerRSI"
STRATEGY_BEAR = "VolatilityBreakout"
STRATEGY_NEUTRAL = "MomentumVolumeTrend"  # Default

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def fetch_data():
    """
    Fetch daily OHLCV data for BTC/USDT from KuCoin (public API).
    """
    logger.info(f"Fetching {LIMIT} {TIMEFRAME} candles for {PAIR}...")
    exchange = ccxt.kucoin()
    try:
        ohlcv = exchange.fetch_ohlcv(PAIR, timeframe=TIMEFRAME, limit=LIMIT)
        df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["date"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        return df
    except Exception as e:
        logger.error(f"Failed to fetch data: {e}")
        sys.exit(1)


def analyze_regime(df):
    """
    Calculate indicators and determine regime.
    """
    # Calculate Indicators
    df["ema200"] = ta.EMA(df, timeperiod=200)
    df["adx"] = ta.ADX(df, timeperiod=14)

    last = df.iloc[-1]

    price = last["close"]
    ema200 = last["ema200"]
    adx = last["adx"]

    logger.info(
        f"Analysis - Date: {last['date']}, Price: {price:.2f}, "
        f"EMA200: {ema200:.2f}, ADX: {adx:.2f}"
    )

    # Determine Regime
    if price < ema200:
        return "BEAR", STRATEGY_BEAR, True  # Bear -> Shorts Enabled
    elif adx > 25:
        # Bull if Price > EMA200 (implied by elif)
        return "BULL", STRATEGY_BULL, False  # Bull -> Longs Only
    elif adx < 20:
        return "SIDEWAYS", STRATEGY_SIDEWAYS, True  # Sideways -> Long/Short
    else:
        return "NEUTRAL", STRATEGY_NEUTRAL, False  # Neutral -> Default (Bullish bias)


def update_config(strategy, allow_short):
    """
    Update config_production.json with the new strategy and unidirectional setting.
    """
    if not CONFIG_PATH.exists():
        logger.error(f"Config file {CONFIG_PATH} not found!")
        sys.exit(1)

    try:
        with CONFIG_PATH.open("r") as f:
            config = json.load(f)

        current_strategy = config.get("strategy")
        current_unidirectional = config.get("unidirectional_only", True)
        target_unidirectional = not allow_short  # unidirectional=True means NO shorts

        if current_strategy == strategy and current_unidirectional == target_unidirectional:
            logger.info("Config is already up to date.")
            return False

        logger.info(
            f"Updating config: Strategy {current_strategy} -> {strategy}, "
            f"Unidirectional {current_unidirectional} -> {target_unidirectional}"
        )

        config["strategy"] = strategy
        config["unidirectional_only"] = target_unidirectional

        with CONFIG_PATH.open("w") as f:
            json.dump(config, f, indent=4)

        return True
    except Exception as e:
        logger.error(f"Failed to update config: {e}")
        sys.exit(1)


def log_decision(regime, strategy, price, ema200, adx):
    """
    Append to regime_log.md.
    """
    date_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

    if not LOG_FILE.exists():
        with LOG_FILE.open("w") as f:
            f.write("| Date | Price | EMA200 | ADX | Regime | Strategy | Action |\n")
            f.write("|---|---|---|---|---|---|---|\n")

    with LOG_FILE.open("a") as f:
        f.write(
            f"| {date_str} | {price:.2f} | {ema200:.2f} | {adx:.2f} | "
            f"{regime} | {strategy} | Switched to {regime} Mode |\n"
        )


def git_commit(changed_files, message):
    """
    Commit changes to git.
    """
    try:
        subprocess.run(
            ["git", "config", "user.name", "github-actions[bot]"], check=False
        )
        subprocess.run(
            [
                "git",
                "config",
                "user.email",
                "github-actions[bot]@users.noreply.github.com"
            ],
            check=False
        )

        for file in changed_files:
            # Force add in case config is gitignored
            subprocess.run(["git", "add", "-f", str(file)], check=True)

        # Check if there are changes to commit
        status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
        if not status.stdout.strip():
            logger.info("No changes to commit.")
            return

        subprocess.run(["git", "commit", "-m", message], check=True)

        # Push to current branch
        # In CI, we need to handle remote.
        # Assuming checkout with persist-credentials: true
        # Push to HEAD:main to handle detached HEAD state in CI
        subprocess.run(["git", "push", "origin", "HEAD:main"], check=True)
        logger.info("Changes pushed to repository.")

    except subprocess.CalledProcessError as e:
        logger.error(f"Git operation failed: {e}")


def main():
    df = fetch_data()
    regime, strategy, allow_short = analyze_regime(df)

    logger.info(f"Detected Regime: {regime}. Strategy: {strategy}. Shorts Allowed: {allow_short}")

    updated = update_config(strategy, allow_short)

    last = df.iloc[-1]
    log_decision(regime, strategy, last["close"], last["ema200"], last["adx"])

    if updated:
        # Only commit if config changed?
        # Or always commit log?
        # Let's commit log and config if updated.
        git_commit(
            [CONFIG_PATH, LOG_FILE],
            f"chore(regime): switched to {strategy} ({regime})"
        )
    else:
        # Even if config didn't change, we might want to log the check?
        # Maybe skip commit if no change to avoid noise.
        # But log file changed.
        git_commit([LOG_FILE], f"chore(regime): checked regime ({regime}) - no change")


if __name__ == "__main__":
    main()
