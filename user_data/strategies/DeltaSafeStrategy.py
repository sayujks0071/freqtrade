"""
DeltaSafeStrategy
A basic strategy for Delta Exchange Futures ensuring compliance with the stack.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Add _base to path to allow import
sys.path.append(str(Path(__file__).parent / "_base"))

import talib.abstract as ta  # noqa: E402
from pandas import DataFrame  # noqa: E402

from freqtrade.strategy import IStrategy  # noqa: E402

from AuditedStrategyMixin import AuditedStrategyMixin  # noqa: E402


class DeltaSafeStrategy(IStrategy, AuditedStrategyMixin):
    INTERFACE_VERSION = 3

    # Minimal ROI
    minimal_roi = {
        "60": 0.01,
        "30": 0.02,
        "0": 0.04
    }

    # Stoploss
    stoploss = -0.10

    # Timeframe
    timeframe = '1h'

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
        'entry': 'limit',
        'exit': 'limit',
        'stoploss': 'market',
        'stoploss_on_exchange': False
    }

    # Order time in force.
    order_time_in_force = {
        'entry': 'GTC',
        'exit': 'GTC'
    }

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # RSI
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        if not self.check_whitelist(metadata['pair']):
            return dataframe

        dataframe.loc[
            (
                (dataframe['rsi'] < 30) &
                (dataframe['volume'] > 0)
            ),
            'enter_long'] = 1

        # Log signal check (manual for now as vectorization is fast)
        # In live mode, we might want to log if a signal is generated for the current candle.

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe['rsi'] > 70) &
                (dataframe['volume'] > 0)
            ),
            'exit_long'] = 1
        return dataframe

    def confirm_trade_entry(
        self,
        pair: str,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        current_time,
        entry_tag,
        side: str,
        **kwargs,
    ) -> bool:
        """
        Called right before placing a trade.
        """
        self.log_signal(pair, self.timeframe, side, "Signal Confirmed", current_time)
        return True
