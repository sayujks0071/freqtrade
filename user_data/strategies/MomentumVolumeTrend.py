"""
MomentumVolumeTrend Strategy
Designed for Bull Markets where Price > EMA200 and ADX > 25.
"""

import sys
from pathlib import Path

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import IStrategy


# Add _base to path to allow import
sys.path.append(str(Path(__file__).parent / "_base"))
from AuditedStrategyMixin import AuditedStrategyMixin  # noqa: E402, RUF100


class MomentumVolumeTrend(IStrategy, AuditedStrategyMixin):
    INTERFACE_VERSION = 3

    # Minimal ROI
    minimal_roi = {"60": 0.01, "30": 0.02, "0": 0.04}

    # Stoploss
    stoploss = -0.10

    # Timeframe
    timeframe = "1h"

    # Run "populate_indicators" only for new candle
    process_only_new_candles = True

    # These values can be overridden in the "ask_strategy" section in the config.
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    # Number of candles the strategy requires before producing valid signals
    startup_candle_count: int = 200

    # Optional order type mapping.
    order_types = {
        "entry": "limit",
        "exit": "limit",
        "stoploss": "market",
        "stoploss_on_exchange": False,
    }

    # Order time in force.
    order_time_in_force = {"entry": "GTC", "exit": "GTC"}

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # EMA 200 for trend filter
        dataframe["ema_200"] = ta.EMA(dataframe, timeperiod=200)
        # EMA 50 for entry signal
        dataframe["ema_50"] = ta.EMA(dataframe, timeperiod=50)
        # ADX for trend strength
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        # RSI for overbought/oversold check
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        if not self.check_whitelist(metadata["pair"]):
            return dataframe

        dataframe.loc[
            (
                (dataframe["close"] > dataframe["ema_200"])
                & (dataframe["adx"] > 25)
                & (dataframe["volume"] > 0)
                & (dataframe["rsi"] < 70)  # Don't buy if overbought
            ),
            "enter_long",
        ] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["close"] < dataframe["ema_50"])  # Trend broken
                | (dataframe["adx"] < 20)  # Trend lost strength
            ),
            "exit_long",
        ] = 1
        return dataframe
