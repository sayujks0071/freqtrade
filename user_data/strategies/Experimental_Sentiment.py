
import sys
from pathlib import Path

import numpy as np
import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import IStrategy, IntParameter

# Add _base to path to allow import
sys.path.append(str(Path(__file__).parent / "_base"))
from AuditedStrategyMixin import AuditedStrategyMixin  # noqa: E402


class Experimental_Sentiment(IStrategy, AuditedStrategyMixin):
    """
    Experimental strategy that uses a mocked "Sentiment" signal
    derived deterministically from volume data to simulate external alpha.
    """
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
    timeframe = "1h"

    # Run "populate_indicators" only for new candle
    process_only_new_candles = True

    # These values can be overridden in the "ask_strategy" section in the config.
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    # Number of candles the strategy requires before producing valid signals
    startup_candle_count: int = 30

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Mocking an external "Sentiment" signal.
        # We use volume modulo operations to create a deterministic but "random-looking" signal
        # between 0.0 and 1.0.
        # Logic: sentiment = (volume % 1000) / 1000.0
        # This simulates a signal that is uncorrelated with price action (mostly).

        # Ensure volume is integer for modulo
        vol_int = dataframe['volume'].fillna(0).astype('int64')

        # Create the mock signal
        dataframe['sentiment'] = (vol_int % 1000) / 1000.0

        # Add RSI for reference (standard practice)
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        if not self.check_whitelist(metadata["pair"]):
            return dataframe

        # Enter Long if Sentiment is High (e.g., > 0.8) representing "High Twitter Hype"
        # We also add a basic filter (Volume > 0)
        dataframe.loc[
            (
                (dataframe['sentiment'] > 0.8) &
                (dataframe['volume'] > 0)
            ),
            'enter_long'] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Exit Long if Sentiment drops (e.g., < 0.2) representing "Negative Sentiment"
        dataframe.loc[
            (
                (dataframe['sentiment'] < 0.2) &
                (dataframe['volume'] > 0)
            ),
            'exit_long'] = 1

        return dataframe
