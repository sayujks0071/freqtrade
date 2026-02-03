import sys
from pathlib import Path

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import IStrategy


# Add _base to path to allow import
sys.path.append(str(Path(__file__).parent / "_base"))
from AuditedStrategyMixin import AuditedStrategyMixin


class VolatilityBreakout(IStrategy, AuditedStrategyMixin):
    INTERFACE_VERSION = 3
    minimal_roi = {"0": 100.0}
    stoploss = -0.10
    timeframe = "1h"
    process_only_new_candles = True
    startup_candle_count = 200

    # Enable shorting
    can_short = True

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema_200"] = ta.EMA(dataframe, timeperiod=200)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            ((dataframe["close"] < dataframe["ema_200"]) & (dataframe["volume"] > 0)),
            "enter_short",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            ((dataframe["close"] > dataframe["ema_200"]) & (dataframe["volume"] > 0)), "exit_short"
        ] = 1
        return dataframe
