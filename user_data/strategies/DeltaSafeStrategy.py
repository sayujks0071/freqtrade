"""
DeltaSafeStrategy module.
"""

# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
# flake8: noqa: F401
# isort: skip_file
# --- Do not remove these libs ---
from pandas import DataFrame
from freqtrade.strategy import IStrategy, IntParameter
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

# Add _base to path to import AuditedStrategyMixin
# This handles both running from root and running via freqtrade
base_path = Path(__file__).parent / "_base"
if str(base_path) not in sys.path:
    sys.path.append(str(base_path))

try:
    from AuditedStrategyMixin import AuditedStrategyMixin
except ImportError:
    # If the file is directly in strategies folder or tests
    try:
        from user_data.strategies._base.AuditedStrategyMixin import AuditedStrategyMixin
    except ImportError:
        # Fallback if structure is flattened or strictly controlled
        pass


class DeltaSafeStrategy(AuditedStrategyMixin, IStrategy):
    """
    DeltaSafeStrategy

    A sample strategy for Delta Exchange futures.
    - Inherits AuditedStrategyMixin for safety and logging.
    - Uses SMA crossover logic.
    - Strict closed candle processing (Logic runs on closed candles).
    """

    # Strategy interface version - allow new iterations of the strategy interface.
    # Check freqtrade documentation for details.
    INTERFACE_VERSION = 3

    # Minimal ROI designed for the strategy.
    # This attribute will be overridden if the config file contains "minimal_roi".
    minimal_roi = {"60": 0.01, "30": 0.02, "0": 0.04}

    # Optimal stoploss designed for the strategy.
    # This attribute will be overridden if the config file contains "stoploss".
    stoploss = -0.10

    # Trailing stoploss
    trailing_stop = False

    # Timeframe
    timeframe = "5m"

    # Run "populate_indicators" only for new candle.
    process_only_new_candles = True

    # These values can be overridden in the config.
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    # Number of candles the strategy requires before producing valid signals
    startup_candle_count: int = 30

    # Strategy parameters
    buy_rsi = IntParameter(10, 40, default=30, space="buy")
    sell_rsi = IntParameter(60, 90, default=70, space="sell")

    def leverage(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_leverage: float,
        max_leverage: float,
        entry_tag: Optional[str],
        side: str,
        **kwargs,
    ) -> float:
        """
        Customize leverage for each new trade.
        """
        return 2.0

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Adds several different TA indicators to the given DataFrame
        """
        # RSI
        import talib.abstract as ta

        dataframe["rsi"] = ta.RSI(dataframe)
        dataframe["sma_short"] = ta.SMA(dataframe, timeperiod=10)
        dataframe["sma_long"] = ta.SMA(dataframe, timeperiod=30)

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Based on TA indicators, populates the entry signal for the given dataframe
        """

        # Named conditions for readability and audit compliance
        condition_long_rsi = dataframe["rsi"] < self.buy_rsi.value
        condition_long_sma = dataframe["sma_short"] > dataframe["sma_long"]
        condition_volume = dataframe["volume"] > 0

        # Apply entry signal
        dataframe.loc[
            (condition_long_rsi & condition_long_sma & condition_volume), "enter_long"
        ] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Based on TA indicators, populates the exit signal for the given dataframe
        """

        # Named conditions
        condition_exit_rsi = dataframe["rsi"] > self.sell_rsi.value
        condition_exit_sma = dataframe["sma_short"] < dataframe["sma_long"]

        # Apply exit signal
        dataframe.loc[(condition_exit_rsi | condition_exit_sma), "exit_long"] = 1

        return dataframe
