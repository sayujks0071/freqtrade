"""
DeltaSafeStrategy
A basic strategy for Delta Exchange Futures ensuring compliance with the stack.

Strategy Name: DeltaSafeStrategy
Author: Freqtrade
Version: 1.0
Timeframes: 1h
Supported Pair Format: futures
Timezone Rule: UTC
Entry/Exit Definitions: RSI < 30 / RSI > 70
No Repainting: process_only_new_candles = True
"""
from datetime import datetime
from typing import Optional

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import IStrategy

# Import from _base (user_data/strategies/_base)
from _base.AuditedStrategyMixin import AuditedStrategyMixin


class DeltaSafeStrategy(AuditedStrategyMixin, IStrategy):
    INTERFACE_VERSION = 3

    # Minimal ROI
    minimal_roi = {"60": 0.01, "30": 0.02, "0": 0.04}

    # Stoploss
    stoploss = -0.10

    # Timeframe
    timeframe = "1h"

    # Run "populate_indicators" only for new candle
    # Logic runs on closed candle only
    process_only_new_candles = True

    # These values can be overridden in the "ask_strategy" section in the config.
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    # Number of candles the strategy requires before producing valid signals
    startup_candle_count: int = 30

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
        # RSI
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        if not self.check_whitelist(metadata["pair"]):
            return dataframe

        dataframe.loc[((dataframe["rsi"] < 30) & (dataframe["volume"] > 0)), "enter_long"] = 1

        # Log signal check handled by AuditedStrategyMixin.confirm_trade_entry
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[((dataframe["rsi"] > 70) & (dataframe["volume"] > 0)), "exit_long"] = 1
        return dataframe

    # No need to override confirm_trade_entry as Mixin handles it.
    # If we need custom logic, call super().confirm_trade_entry(...)
