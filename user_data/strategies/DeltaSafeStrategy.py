# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
# flake8: noqa: F401
# isort: skip_file
# --- Do not remove these libs ---
from datetime import datetime
import os

import numpy as np
import pandas as pd
from pandas import DataFrame

from freqtrade.strategy import IStrategy, IntParameter

# Import Mixin
# Depending on freqtrade setup, user_data/strategies is in path
try:
    from _base.AuditedStrategyMixin import AuditedStrategyMixin
except ImportError:
    # Fallback if running locally/testing without full context
    import sys

    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from _base.AuditedStrategyMixin import AuditedStrategyMixin


class DeltaSafeStrategy(IStrategy, AuditedStrategyMixin):
    """
    Delta Safe Strategy - Audited & Risk-Managed
    Uses simple SMA crossover with strict auditing.
    """

    INTERFACE_VERSION = 3

    # Minimal ROI designed for the strategy.
    minimal_roi = {"60": 0.01, "30": 0.02, "0": 0.04}

    # Optimal stoploss designed for the strategy.
    stoploss = -0.10

    # Trailing stop:
    trailing_stop = False

    # Run "timeframe" at 5m
    timeframe = "5m"

    # Hyperoptable parameters
    buy_sma_short = IntParameter(3, 50, default=5, space="buy")
    buy_sma_long = IntParameter(10, 100, default=15, space="buy")

    def leverage(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_leverage: float,
        max_leverage: float,
        entry_tag: str,
        side: str,
        **kwargs,
    ) -> float:
        """
        Customize leverage for each new trade.
        """
        # Default to 2x or env var
        return float(os.getenv("LEVERAGE", 2.0))

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # SMA
        dataframe["sma_short"] = dataframe["close"].rolling(self.buy_sma_short.value).mean()
        dataframe["sma_long"] = dataframe["close"].rolling(self.buy_sma_long.value).mean()

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Entry signal logic
        """
        dataframe.loc[
            ((dataframe["sma_short"] > dataframe["sma_long"]) & (dataframe["volume"] > 0)),
            "enter_long",
        ] = 1

        dataframe.loc[
            ((dataframe["sma_short"] < dataframe["sma_long"]) & (dataframe["volume"] > 0)),
            "enter_short",
        ] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Exit signal logic
        """
        dataframe.loc[
            ((dataframe["sma_short"] < dataframe["sma_long"]) & (dataframe["volume"] > 0)),
            "exit_long",
        ] = 1

        dataframe.loc[
            ((dataframe["sma_short"] > dataframe["sma_long"]) & (dataframe["volume"] > 0)),
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
        Override entry confirmation to add audit checks.
        """

        # 1. Audit Log
        self.log_signal(pair, self.timeframe, f"ENTRY {side}")

        # 2. Whitelist Check (Safety)
        if not self.assert_pair_in_whitelist(pair):
            self.audit("BLOCK", pair, "Pair not in whitelist during entry confirmation")
            return False

        # 3. Additional custom checks (e.g. spread, depth) could go here

        return True

    def confirm_trade_exit(
        self,
        pair: str,
        trade: str,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        sell_reason: str,
        current_time: datetime,
        **kwargs,
    ) -> bool:
        self.log_signal(pair, self.timeframe, f"EXIT {sell_reason}")
        return True
