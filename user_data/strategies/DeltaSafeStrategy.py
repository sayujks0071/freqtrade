"""
DeltaSafeStrategy
A basic strategy for Delta Exchange Futures ensuring compliance with the stack.
"""
import sys
from pathlib import Path

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import IStrategy

# Import the mixin
# Freqtrade adds user_data/strategies to sys.path
try:
    from _base.AuditedStrategyMixin import AuditedStrategyMixin
except ImportError:
    # Fallback for local testing or different path structure
    sys.path.append(str(Path(__file__).parent / "_base"))
    from AuditedStrategyMixin import AuditedStrategyMixin


class DeltaSafeStrategy(AuditedStrategyMixin, IStrategy):
    """
    DeltaSafeStrategy:
    - Inherits AuditedStrategyMixin for safety (audit logs, whitelist check)
    - Inherits IStrategy for Freqtrade logic
    - Logic runs on closed candles.
    """
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
        dataframe["volume"] = dataframe["volume"]  # Ensure volume exists
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Check whitelist first (optional, as mixin handles trade entry check)
        # But good to skip processing if not needed
        # self.assert_pair_in_whitelist(metadata["pair"]) # Can't call here easily without warnings

        dataframe.loc[
            ((dataframe["rsi"] < 30) & (dataframe["volume"] > 0)),
            "enter_long"
        ] = 1

        # Short signal
        dataframe.loc[
            ((dataframe["rsi"] > 70) & (dataframe["volume"] > 0)),
            "enter_short"
        ] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Long exit
        dataframe.loc[
            ((dataframe["rsi"] > 70) & (dataframe["volume"] > 0)),
            "exit_long"
        ] = 1

        # Short exit
        dataframe.loc[
            ((dataframe["rsi"] < 30) & (dataframe["volume"] > 0)),
            "exit_short"
        ] = 1

        return dataframe

    # We do NOT implement confirm_trade_entry here, so the Mixin's version is used.
    # Mixin handles logging and whitelist verification.
