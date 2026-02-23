"""
VolatilityBreakout Strategy
Designed for Volatile/Crashing Markets where Price < EMA200.
Enables Shorting.
"""

import sys
from pathlib import Path

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import IStrategy


# Add _base to path to allow import
sys.path.append(str(Path(__file__).parent / "_base"))
from AuditedStrategyMixin import AuditedStrategyMixin  # noqa: E402


class VolatilityBreakout(IStrategy, AuditedStrategyMixin):
    INTERFACE_VERSION = 3

    # Minimal ROI
    minimal_roi = {"60": 0.01, "30": 0.02, "0": 0.04}

    # Stoploss
    stoploss = -0.10

    # Timeframe
    timeframe = "1h"

    # Enable Shorting
    can_short = True

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

        # ADX/ATR could be added for volatility confirmation if needed
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        if not self.check_whitelist(metadata["pair"]):
            return dataframe

        # Short entry logic: Price below EMA200 (Bearish)
        dataframe.loc[
            ((dataframe["close"] < dataframe["ema_200"]) & (dataframe["volume"] > 0)),
            "enter_short",
        ] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Exit Short if Price recovers above EMA200
        dataframe.loc[
            (dataframe["close"] > dataframe["ema_200"]),
            "exit_short",
        ] = 1
        return dataframe
