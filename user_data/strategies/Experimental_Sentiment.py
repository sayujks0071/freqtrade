"""
Experimental_Sentiment Strategy
Attempts to find new alpha by mocking "Sentiment Analysis" and "On-Chain Metrics".
"""

import sys
from pathlib import Path

import numpy as np  # noqa: F401
import talib
import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import IStrategy


# Add _base to path to allow import
sys.path.append(str(Path(__file__).parent / "_base"))
from AuditedStrategyMixin import AuditedStrategyMixin  # noqa: E402, RUF100


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
        # Mock "Whale Wallet Movements" using MFI (Money Flow Index)
        # Low MFI indicates accumulation (whales buying low)
        # High MFI indicates distribution (whales selling high)
        dataframe["whale_index"] = ta.MFI(dataframe, timeperiod=14)

        # Mock "Twitter Volume" using Volume SMA
        # High relative volume indicates social chatter / attention
        # Using talib directly to calculate SMA on volume column
        dataframe["volume_sma"] = talib.SMA(dataframe["volume"], timeperiod=20)
        dataframe["twitter_volume"] = dataframe["volume"] / dataframe["volume_sma"]

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Long if Whales are accumulating (MFI < 30) AND Twitter is buzzing (Volume > SMA)
        dataframe.loc[
            ((dataframe["whale_index"] < 30) & (dataframe["twitter_volume"] > 1.0)), "enter_long"
        ] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Exit if Whales are distributing (MFI > 70)
        dataframe.loc[(dataframe["whale_index"] > 70), "exit_long"] = 1
        return dataframe
