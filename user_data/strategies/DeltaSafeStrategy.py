"""
DeltaSafeStrategy
A basic strategy for Delta Exchange Futures ensuring compliance with the stack.
"""

import sys
from pathlib import Path

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import IStrategy  # noqa: F401


# Add _base to path to allow import
sys.path.append(str(Path(__file__).parent / "_base"))
try:
    from AuditedStrategyMixin import AuditedStrategyMixin
except ImportError:
    # Fallback for testing or if mixin not found, to avoid crashing during inspection
    # though it will fail at runtime if not present.
    # In strict mode we might want to fail hard.
    class AuditedStrategyMixin:  # type: ignore
        pass


class DeltaSafeStrategy(AuditedStrategyMixin):
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
        # In a real scenario, check_whitelist would be called here if implemented in Mixin
        # For now, we assume the pair is valid or checked elsewhere.

        dataframe.loc[((dataframe["rsi"] < 30) & (dataframe["volume"] > 0)), "enter_long"] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[((dataframe["rsi"] > 70) & (dataframe["volume"] > 0)), "exit_long"] = 1
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
        # Call super which logs the entry via Mixin
        return super().confirm_trade_entry(
            pair=pair,
            order_type=order_type,
            amount=amount,
            rate=rate,
            time_in_force=time_in_force,
            current_time=current_time,
            entry_tag=entry_tag,
            side=side,
            **kwargs,
        )
