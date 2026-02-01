"""
Experimental_Sentiment
A strategy that uses a mock sentiment signal (e.g. "Twitter Volume" or "Whale Wallet Movements").
"""

import sys
from datetime import datetime
from pathlib import Path

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import IStrategy


# Add _base to path to allow import
sys.path.append(str(Path(__file__).parent / "_base"))
from AuditedStrategyMixin import AuditedStrategyMixin


class Experimental_Sentiment(IStrategy, AuditedStrategyMixin):
    INTERFACE_VERSION = 3

    # Minimal ROI
    minimal_roi = {"60": 0.01, "30": 0.02, "0": 0.04}

    # Stoploss
    stoploss = -0.10

    # Timeframe
    timeframe = "1h"

    # Run "populate_indicators" only for new candle
    process_only_new_candles = True

    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    startup_candle_count: int = 30

    order_types = {
        "entry": "limit",
        "exit": "limit",
        "stoploss": "market",
        "stoploss_on_exchange": False,
    }

    order_time_in_force = {"entry": "GTC", "exit": "GTC"}

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Standard TA for reference
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)

        # Mock Sentiment Signal
        # Use Volume as a seed for pseudo-randomness to avoid repainting
        # (volume is consistent for closed candles)
        # We take the volume, multiply by a prime, and take modulo to get a 0-1 score
        dataframe["sentiment_score"] = (dataframe["volume"] * 0.123456789) % 1

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        if not self.check_whitelist(metadata["pair"]):
            return dataframe

        # Entry logic based on Sentiment
        dataframe.loc[
            (
                (dataframe["sentiment_score"] > 0.8)  # High sentiment -> Buy
                & (dataframe["volume"] > 0)
            ),
            "enter_long",
        ] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Exit logic based on Sentiment
        dataframe.loc[
            (
                (dataframe["sentiment_score"] < 0.2)  # Low sentiment -> Sell
                & (dataframe["volume"] > 0)
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
        current_time: datetime,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> bool:
        self.log_signal(pair, self.timeframe, side, "Sentiment Entry Confirmed", current_time)
        return True
