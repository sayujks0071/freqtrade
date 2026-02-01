import sys
from pathlib import Path

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import IStrategy


# Add _base to path to allow import
sys.path.append(str(Path(__file__).parent / "_base"))
from AuditedStrategyMixin import AuditedStrategyMixin  # noqa: E402, RUF100


class VolatilityBreakout(IStrategy, AuditedStrategyMixin):
    INTERFACE_VERSION = 3
    can_short = True
    minimal_roi = {"0": 0.1}
    stoploss = -0.10
    timeframe = "1h"

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["atr"] = ta.ATR(dataframe)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Short if price < EMA200 (Regime: Volatile/Crashing)
        dataframe.loc[(dataframe["close"] < dataframe["ema200"]), "enter_short"] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[(dataframe["close"] > dataframe["ema200"]), "exit_short"] = 1
        return dataframe
