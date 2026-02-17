"""
DeltaSafeStrategy
A basic strategy for Delta Exchange Futures ensuring compliance with the stack.

Strategy Name: DeltaSafeStrategy
Author: Google Jules
Version: 1.0.0
Supported Timeframes: 1h
Supported Pair Format: BASE/QUOTE:SETTLE
Timezone: UTC
Entry Conditions: RSI < 30 and Volume > 0
Exit Conditions: RSI > 70 and Volume > 0
No Repainting: True
"""

from datetime import datetime
from typing import Optional

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import IStrategy
from _base.AuditedStrategyMixin import AuditedStrategyMixin


class DeltaSafeStrategy(IStrategy, AuditedStrategyMixin):
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
        """
        Populate indicators.
        """
        # RSI
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Populate entry trend.
        """
        # Ensure pair is in whitelist (Audit Check)
        if not self.assert_pair_in_whitelist(metadata["pair"]):
            return dataframe

        dataframe.loc[((dataframe["rsi"] < 30) & (dataframe["volume"] > 0)), "enter_long"] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Populate exit trend.
        """
        dataframe.loc[((dataframe["rsi"] > 70) & (dataframe["volume"] > 0)), "exit_long"] = 1
        return dataframe

    def confirm_trade_entry(
        self,
        pair: str,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        current_time: datetime,
        entry_tag: Optional[str],
        side: str,
        **kwargs,
    ) -> bool:
        """
        Called right before placing a trade.
        """
        # 1. Check Daily Loss Limit (Audit Check)
        if not self.check_daily_loss_limit(current_time):
            self.log_signal(pair, self.timeframe, side, "Daily Loss Limit Hit", current_time)
            return False

        # 2. Log Signal
        # Fetch indicator value for log
        # This is expensive? Using get_analyzed_dataframe() to get latest candle.
        # But confirm_trade_entry is called per trade, so ok.
        try:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            last_candle = dataframe.iloc[-1].squeeze()
            rsi_val = last_candle.get("rsi", 0)
            indicators = {"rsi": rsi_val}
        except Exception:
            indicators = {}

        self.log_signal(
            pair, self.timeframe, side, "Signal Confirmed", current_time, indicators=indicators
        )
        return True
