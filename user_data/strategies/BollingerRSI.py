import sys
from pathlib import Path

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import IStrategy


# Add _base to path to allow import
sys.path.append(str(Path(__file__).parent / "_base"))
from AuditedStrategyMixin import AuditedStrategyMixin


class BollingerRSI(IStrategy, AuditedStrategyMixin):
    INTERFACE_VERSION = 3
    minimal_roi = {"0": 0.05}
    stoploss = -0.05
    timeframe = "1h"

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["rsi"] = ta.RSI(dataframe)
        bollinger = ta.BBANDS(dataframe, timeperiod=20, nbdevup=2.0, nbdevdn=2.0)
        dataframe["bb_lowerband"] = bollinger["lowerband"]
        dataframe["bb_upperband"] = bollinger["upperband"]
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["rsi"] < 30) & (dataframe["close"] < dataframe["bb_lowerband"]), "enter_long"
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["rsi"] > 70) | (dataframe["close"] > dataframe["bb_upperband"]), "exit_long"
        ] = 1
        return dataframe
