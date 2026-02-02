"""
DeltaSafeStrategy
A strategy with safety built-in for Delta Exchange.
"""
import logging
import sys
from pathlib import Path

# Add _base to path to allow import
sys.path.append(str(Path(__file__).parent / "_base"))

import talib.abstract as ta  # noqa: E402
from AuditedStrategyMixin import AuditedStrategyMixin  # noqa: E402
from pandas import DataFrame  # noqa: E402

from freqtrade.strategy import IStrategy  # noqa: E402


logger = logging.getLogger(__name__)


class DeltaSafeStrategy(IStrategy, AuditedStrategyMixin):
    """
    DeltaSafeStrategy
    A sample strategy using the AuditedStrategyMixin.
    """

    INTERFACE_VERSION = 3

    # Minimal ROI designed for the strategy.
    # This attribute will be overridden if the config file contains "minimal_roi".
    minimal_roi = {"60": 0.01, "30": 0.02, "0": 0.04}

    # Optimal stoploss designed for the strategy.
    # This attribute will be overridden if the config file contains "stoploss".
    stoploss = -0.10

    # Trailing stop
    trailing_stop = False

    # Hyperspace parameters:
    # buy_rsi = IntParameter(low=1, high=50, default=30, space='buy', optimize=True, load=True)
    # sell_rsi = IntParameter(low=50, high=100, default=70, space='sell', optimize=True, load=True)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Adds several different TA indicators to the given DataFrame
        """
        # RSI
        dataframe["rsi"] = ta.RSI(dataframe)

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Based on TA indicators, populates the entry signal for the given dataframe
        """
        dataframe.loc[
            (
                (dataframe["rsi"] < 30) & (dataframe["volume"] > 0)
            ),
            "enter_long",
        ] = 1

        # Log signal check (manual for now as vectorization is fast)
        # In live mode, we might want to log if a signal is generated for the current candle.
        # But logging every candle is too much.
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Based on TA indicators, populates the exit signal for the given dataframe
        """
        dataframe.loc[
            (
                (dataframe["rsi"] > 70) & (dataframe["volume"] > 0)
            ),
            "exit_long",
        ] = 1
        return dataframe

    def confirm_trade_entry(
        self,
        pair: str,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        current_time: object,
        entry_tag: object,
        side: str,
        **kwargs,
    ) -> bool:
        """
        Called right before placing a trade.
        """
        # Audit logging from mixin
        self.log_signal(
            pair=pair,
            timeframe=self.timeframe,
            direction=side,
            reason=entry_tag or "strategy_signal",
            candle_date=current_time,
        )

        return self.check_whitelist(pair)
