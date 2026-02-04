"""
Experimental_Sentiment
Experimental Strategy exploring 'Whale Sentiment' via Volume Anomalies.
Hypothesis: Unusual volume spikes precede price movements.
"""

import sys
from pathlib import Path

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import IStrategy


# Add _base to path to allow import
sys.path.append(str(Path(__file__).parent / "_base"))
from AuditedStrategyMixin import AuditedStrategyMixin  # noqa: E402, RUF100


class Experimental_Sentiment(IStrategy, AuditedStrategyMixin):
    """
    Experimental Strategy exploring 'Whale Sentiment' via Volume Anomalies.
    Hypothesis: Unusual volume spikes precede price movements.
    """

    INTERFACE_VERSION = 3

    # Minimal ROI
    minimal_roi = {"60": 0.01, "30": 0.02, "0": 0.04}

    # Stoploss
    stoploss = -0.10

    # Timeframe
    timeframe = "1h"

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

    def populate_indicators(
        self, dataframe: DataFrame, metadata: dict
    ) -> DataFrame:
        # RSI
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)

        # Volume MA using pandas
        dataframe["volume_ma"] = dataframe["volume"].rolling(window=24).mean()

        # Whale Sentiment: Volume > 2.0 * Volume MA
        dataframe["whale_sentiment"] = (
            dataframe["volume"] > (dataframe["volume_ma"] * 2.0)
        ).astype(int)

        return dataframe

    def populate_entry_trend(
        self, dataframe: DataFrame, metadata: dict
    ) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["whale_sentiment"] == 1)
                & (dataframe["rsi"] < 70)  # Filter out extreme overbought
            ),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(
        self, dataframe: DataFrame, metadata: dict
    ) -> DataFrame:
        dataframe.loc[
            (dataframe["rsi"] > 70),
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
        current_time,
        entry_tag,
        side: str,
        **kwargs,
    ) -> bool:
        self.log_signal(
            pair, self.timeframe, side, "Whale Signal Confirmed", current_time
        )
        return True
