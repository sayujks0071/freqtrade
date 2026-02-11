"""
Experimental_Sentiment
A strategy that simulates an external signal (mocked via lookahead)
to demonstrate the potential of "Twitter Volume" or "Whale Wallet Movements".
"""

from pandas import DataFrame

from freqtrade.strategy import IStrategy


class Experimental_Sentiment(IStrategy):
    INTERFACE_VERSION = 3

    # Minimal ROI - set to very high to rely on exit signal
    minimal_roi = {"0": 100}

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
        """
        Populate indicators.
        Here we mock the "Twitter Volume" signal.
        """
        # MOCK SIGNAL: Simulating high Twitter volume preceding a pump.
        # We use a lookahead (shift(-1)) to determine if the next candle is bullish.
        # This creates a "perfect" predictive signal for demonstration purposes.
        dataframe["twitter_volume"] = (dataframe["close"].shift(-1) > dataframe["close"]).astype(
            int
        )

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Based on the mock signal, enter long if the next candle is expected to be green.
        """
        dataframe.loc[
            (
                (dataframe["twitter_volume"] == 1)  # Next candle is up
                & (dataframe["volume"] > 0)  # Make sure there is volume
            ),
            "enter_long",
        ] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Exit if the mock signal indicates the next candle is red.
        """
        dataframe.loc[
            (
                (dataframe["twitter_volume"] == 0)  # Next candle is down
                & (dataframe["volume"] > 0)
            ),
            "exit_long",
        ] = 1

        return dataframe
