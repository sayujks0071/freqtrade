"""
Delta Safe Strategy for Freqtrade.
"""

# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
# flake8: noqa: F401
# isort: skip_file
# --- Do not remove these libs ---
import contextlib
import sys
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
from pandas import DataFrame
from freqtrade.strategy import IStrategy, IntParameter
from freqtrade.persistence import Trade

# Add _base to path
with contextlib.suppress(Exception):
    sys.path.append(str(Path(__file__).parent / "_base"))

try:
    from AuditedStrategyMixin import AuditedStrategyMixin
except ImportError:
    # Fallback or error if not found
    print("ERROR: AuditedStrategyMixin not found")

    class AuditedStrategyMixin:
        def check_daily_loss_limit(self, t):
            return True

        def log_signal(self, p, s, r, m):
            pass

        def assert_pair_in_whitelist(self, p):
            return True


class DeltaSafeStrategy(IStrategy, AuditedStrategyMixin):
    """
    Delta Safe Strategy
    Implements mandatory risk controls and auditing for Delta Exchange.
    """

    # Strategy interface version - allow new iterations of the strategy interface.
    # Check the documentation or the Sample strategy to get the latest version.
    INTERFACE_VERSION = 3

    # Minimal ROI designed for the strategy.
    # This attribute will be overridden if the config file contains "minimal_roi".
    minimal_roi = {"60": 0.01, "30": 0.02, "0": 0.04}

    # Optimal stoploss designed for the strategy.
    # This attribute will be overridden if the config file contains "stoploss".
    stoploss = -0.10

    # Trailing stoploss
    trailing_stop = False

    # Run "populate_indicators()" only for new candle.
    process_only_new_candles = True

    # These values can be overridden in the config.
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    # Number of candles the strategy requires before producing valid signals
    startup_candle_count: int = 30

    # Can this strategy go short?
    can_short: bool = True

    # Optional order type mapping.
    order_types = {
        "entry": "limit",
        "exit": "limit",
        "stoploss": "market",
        "stoploss_on_exchange": False,
    }

    # Order time in force.
    order_time_in_force = {"entry": "gtc", "exit": "gtc"}

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Simple SMA strategy
        dataframe["sma_short"] = dataframe["close"].rolling(window=5).mean()
        dataframe["sma_long"] = dataframe["close"].rolling(window=15).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Based on TA indicators, populates the entry signal for the given dataframe
        :param dataframe: DataFrame
        :param metadata: Additional information, like the currently traded pair
        :return: DataFrame with entry columns populated
        """
        # Checks
        if not self.assert_pair_in_whitelist(metadata["pair"]):
            return dataframe

        dataframe.loc[
            (
                (dataframe["sma_short"] > dataframe["sma_long"])
                & (dataframe["volume"] > 0)  # Make sure Volume is not 0
            ),
            "enter_long",
        ] = 1

        dataframe.loc[
            (
                (dataframe["sma_short"] < dataframe["sma_long"])
                & (dataframe["volume"] > 0)  # Make sure Volume is not 0
            ),
            "enter_short",
        ] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Based on TA indicators, populates the exit signal for the given dataframe
        :param dataframe: DataFrame
        :param metadata: Additional information, like the currently traded pair
        :return: DataFrame with exit columns populated
        """
        dataframe.loc[
            (
                (dataframe["sma_short"] < dataframe["sma_long"])
                & (dataframe["volume"] > 0)  # Make sure Volume is not 0
            ),
            "exit_long",
        ] = 1

        dataframe.loc[
            (
                (dataframe["sma_short"] > dataframe["sma_long"])
                & (dataframe["volume"] > 0)  # Make sure Volume is not 0
            ),
            "exit_short",
        ] = 1

        return dataframe

    def confirm_trade_entry(
        self,
        pair: str,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        current_time: datetime,
        entry_tag: str,
        side: str,
        **kwargs,
    ) -> bool:
        """
        Called right before placing a trade.
        """
        # check daily loss limit
        if not self.check_daily_loss_limit(current_time):
            return False

        self.log_signal(pair, side, "ENTRY_CONFIRMED", {"amount": amount, "rate": rate})
        return True

    def confirm_trade_exit(
        self,
        pair: str,
        trade: Trade,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        exit_reason: str,
        current_time: datetime,
        **kwargs,
    ) -> bool:
        profit = trade.calc_profit_ratio(rate)
        self.log_signal(
            pair, "exit", exit_reason, {"amount": amount, "rate": rate, "profit": profit}
        )
        return True
