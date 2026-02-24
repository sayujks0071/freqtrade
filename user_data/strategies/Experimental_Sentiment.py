import numpy as np
import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import IStrategy


class PureTA_Baseline(IStrategy):
    """
    Pure Technical Analysis Strategy: RSI based.
    """

    INTERFACE_VERSION = 3
    minimal_roi = {"60": 0.01, "30": 0.02, "0": 0.04}
    stoploss = -0.10
    timeframe = "1h"
    process_only_new_candles = True
    startup_candle_count = 30

    order_types = {
        "entry": "limit",
        "exit": "limit",
        "stoploss": "market",
        "stoploss_on_exchange": False,
    }

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[(dataframe["rsi"] < 30) & (dataframe["volume"] > 0), "enter_long"] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[(dataframe["rsi"] > 70) & (dataframe["volume"] > 0), "exit_long"] = 1
        return dataframe


class Experimental_Sentiment(PureTA_Baseline):
    """
    Experimental Strategy: Adds Mocked 'Whale' Sentiment (Volume Z-Score).
    """

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Call parent to get RSI
        super().populate_indicators(dataframe, metadata)

        # Mock "Whale Activity": Volume Z-Score > 2.0
        # Rolling mean/std of volume
        vol_mean = dataframe["volume"].rolling(window=20).mean()
        vol_std = dataframe["volume"].rolling(window=20).std()

        # Avoid division by zero
        dataframe["vol_zscore"] = (dataframe["volume"] - vol_mean) / vol_std
        dataframe["vol_zscore"] = dataframe["vol_zscore"].replace([np.inf, -np.inf], 0).fillna(0)

        # Mock Signal: "Whale Alert" when Z-Score > 2.0
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Require RSI < 30 AND Volume Z-Score > 2.0 (Whale buying dip?)
        dataframe.loc[
            (dataframe["rsi"] < 30) & (dataframe["vol_zscore"] > 2.0) & (dataframe["volume"] > 0),
            "enter_long",
        ] = 1
        return dataframe
