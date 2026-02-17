"""
Strategy Name: DeltaSafeStrategy
Author: Google Jules
Version: 1.1
Supported Timeframes: 1h
Supported Pair Format: Delta Futures (BTC/USDT:USDT)
Timezone: UTC (datetime.now(timezone.utc))

Entry Conditions:
  - Long: RSI < 30 and Volume > 0
  - Short: None

Exit Conditions:
  - Long: RSI > 70 and Volume > 0
  - Short: None

No Repainting: Logic runs on closed candles only (process_only_new_candles=True)
"""

import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import IStrategy


# Add _base to path to allow import
sys.path.append(str(Path(__file__).parent / "_base"))
from AuditedStrategyMixin import AuditedStrategyMixin  # noqa: E402, RUF100


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
        # Check whitelist first
        if not self.assert_pair_in_whitelist(metadata["pair"]):
            return dataframe

        # Define named variables for clarity
        # RSI oversold condition
        long_rsi = dataframe["rsi"] < 30
        # Volume filter
        long_volume = dataframe["volume"] > 0

        # Combine conditions
        # We enter long when RSI is oversold and we have volume
        dataframe.loc[(long_rsi & long_volume), "enter_long"] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Define named variables for clarity
        # RSI overbought condition
        exit_long_rsi = dataframe["rsi"] > 70
        # Volume filter
        exit_long_volume = dataframe["volume"] > 0

        # We exit long when RSI is overbought and volume is present
        dataframe.loc[(exit_long_rsi & exit_long_volume), "exit_long"] = 1
        return dataframe

    def confirm_trade_entry(
        self,
        pair: str,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        current_time: datetime,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> bool:
        """
        Called right before placing a trade.
        """
        # Call mixin implementation to log audit details
        return super().confirm_trade_entry(
            pair,
            order_type,
            amount,
            rate,
            time_in_force,
            current_time,
            entry_tag,
            side,
            **kwargs,
        )

    def confirm_trade_exit(
        self,
        pair: str,
        trade: Any,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        sell_reason: str,
        current_time: datetime,
        **kwargs,
    ) -> bool:
        """
        Called right before exiting a trade.
        """
        return super().confirm_trade_exit(
            pair,
            trade,
            order_type,
            amount,
            rate,
            time_in_force,
            sell_reason,
            current_time,
            **kwargs,
        )
