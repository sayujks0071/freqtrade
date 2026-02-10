#!/usr/bin/env python3
"""
Regime Switcher Script
"""
import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import talib.abstract as ta


# Add repo root to path
sys.path.append(str(Path(__file__).parent.parent))

try:
    from freqtrade.data.history import load_pair_history
    from freqtrade.enums import CandleType
except ImportError:
    print("Error: Freqtrade not found. Please run this script from the repo root.")
    sys.exit(1)

USER_DATA_DIR = Path("user_data")
CONFIG_FILE = USER_DATA_DIR / "configs/config_production.json"
LOG_FILE = Path("regime_log.md")
PAIR = "BTC/USDT"
TIMEFRAME = "1d"
EXCHANGE = "kucoin"  # Reliable public data


def run_command(cmd):
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        return False
    return True


def download_data():
    # Calculate start date dynamically (365 days ago) to ensure enough data for EMA200
    start_date = (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")
    timerange = f"{start_date}-"

    cmd = [
        sys.executable,
        "-m",
        "freqtrade",
        "download-data",
        "--exchange",
        EXCHANGE,
        "--pairs",
        PAIR,
        "--timeframe",
        TIMEFRAME,
        "--timerange",
        timerange,
        "--data-format-ohlcv",
        "json",
    ]
    return run_command(cmd)


def get_regime(dataframe):
    # Calculate indicators
    dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
    dataframe["adx"] = ta.ADX(dataframe)

    last_candle = dataframe.iloc[-1]

    price = last_candle["close"]
    ema200 = last_candle["ema200"]
    adx = last_candle["adx"]

    print(
        f"Analysis for {last_candle['date']}: Price={price:.2f}, EMA200={ema200:.2f}, ADX={adx:.2f}"
    )

    if pd.isna(ema200) or pd.isna(adx):
        return "BollingerRSI", "Insufficient Data (NaN Indicators)"

    if adx < 20:
        return "BollingerRSI", "Sideways/Choppy (ADX < 20)"
    elif price > ema200 and adx > 25:
        return "MomentumVolumeTrend", "Bull Market (Price > EMA200, ADX > 25)"
    elif price < ema200:
        return "VolatilityBreakout", "Bear/Volatile (Price < EMA200)"
    else:
        return "BollingerRSI", "Uncertain/Weak Trend (Defaulting to Sideways)"


def update_config(new_strategy):
    if not CONFIG_FILE.exists():
        print(f"Config file not found: {CONFIG_FILE}")
        return False

    with CONFIG_FILE.open("r") as f:
        config = json.load(f)

    current_strategy = config.get("strategy")

    if current_strategy == new_strategy:
        print(f"Strategy is already {new_strategy}. No change needed.")
        return False

    config["strategy"] = new_strategy

    with CONFIG_FILE.open("w") as f:
        json.dump(config, f, indent=4)

    print(f"Updated config strategy to {new_strategy}")
    return True


def log_decision(strategy, reason):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"| {timestamp} | {strategy} | {reason} |\n"

    if not LOG_FILE.exists():
        with LOG_FILE.open("w") as f:
            f.write("| Date | Strategy | Reason |\n")
            f.write("|---|---|---|\n")

    with LOG_FILE.open("a") as f:
        f.write(log_entry)
    print(f"Logged decision to {LOG_FILE}")


def main():
    print("Starting Regime Detection...")

    # 1. Download Data
    if not download_data():
        print("Failed to download data.")
        sys.exit(1)

    # 2. Load Data
    datadir = USER_DATA_DIR / "data" / EXCHANGE

    try:
        data = load_pair_history(
            pair=PAIR,
            timeframe=TIMEFRAME,
            datadir=datadir,
            candle_type=CandleType.SPOT,
            data_format="json",
        )
    except Exception as e:
        print(f"Error loading data: {e}")
        sys.exit(1)

    if data.empty:
        print(f"No data found in {datadir}.")
        sys.exit(1)

    # 3. Determine Regime
    strategy, reason = get_regime(data)

    # 4. Update Config
    changed = update_config(strategy)

    # 5. Log
    if changed:
        log_decision(strategy, f"Switched: {reason}")
    else:
        print("Regime unchanged.")
        # log_decision(strategy, f"Maintained: {reason}") # Uncomment to log every run


if __name__ == "__main__":
    main()
