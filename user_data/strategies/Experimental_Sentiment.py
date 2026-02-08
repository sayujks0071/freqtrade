"""
ExperimentalSentiment
A strategy that mocks an external 'Whale Wallet' or 'Sentiment' signal
to test if high-quality external data improves performance.
"""

import numpy as np
import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import IStrategy


class ExperimentalSentiment(IStrategy):
    INTERFACE_VERSION = 3

    # Minimal ROI
    minimal_roi = {"60": 0.01, "30": 0.02, "0": 0.04}

    # Stoploss
    stoploss = -0.10

    # Timeframe
    timeframe = "1h"

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
        "entry": "limit",
        "exit": "limit",
        "stoploss": "market",
        "stoploss_on_exchange": False,
    }

    # Order time in force.
    order_time_in_force = {"entry": "GTC", "exit": "GTC"}

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # RSI (Standard Technical Analysis)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)

        # MOCK SIGNAL: "Whale Wallet Movements"
        # This simulates a high-quality external signal that predicts price movement.
        # We use future data here (shift(-5)) strictly for research purposes to see
        # if such a signal creates alpha. In production, this would be replaced by
        # real API calls or data feeds.

        # If price in 5 candles is higher than current price, whales are buying (1).
        # If price in 5 candles is lower, whales are selling (-1).
        # We use shift(-5) which looks 5 candles into the future.
        future_price = dataframe["close"].shift(-5)
        dataframe["mock_whale_movement"] = np.where(future_price > dataframe["close"], 1, -1)

        # Fill NaN at the end (due to shift) with 0
        dataframe["mock_whale_movement"] = dataframe["mock_whale_movement"].fillna(0)

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Enter Long if Whale Movement is Positive
        dataframe.loc[
            (
                (dataframe["mock_whale_movement"] == 1)  # Whales are buying
                & (dataframe["volume"] > 0)  # Ensure volume exists
            ),
            "enter_long",
        ] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Exit if Whale Movement is Negative
        dataframe.loc[
            (
                (dataframe["mock_whale_movement"] == -1)  # Whales are selling
                & (dataframe["volume"] > 0)
            ),
            "exit_long",
        ] = 1
        return dataframe
