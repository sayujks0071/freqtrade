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
    minimal_roi = {"0": 0.05, "30": 0.02, "60": 0.01}
    stoploss = -0.05
    timeframe = "1h"
    process_only_new_candles = True
    startup_candle_count = 30

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe['adx'] = ta.ADX(dataframe)
        dataframe['rsi'] = ta.RSI(dataframe)
        bollinger = ta.BBANDS(dataframe, timeperiod=20, nbdevup=2.0, nbdevdn=2.0, matype=0)
        dataframe['bb_upper'] = bollinger['upperband']
        dataframe['bb_lower'] = bollinger['lowerband']
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        if not self.check_whitelist(metadata['pair']):
            return dataframe

        # Mean Reversion Logic: Buy when price is low (below lower BB) and oversold (RSI < 30)
        dataframe.loc[
            (
                (dataframe['adx'] < 25) &  # Confirm weak trend
                (dataframe['close'] < dataframe['bb_lower']) &
                (dataframe['rsi'] < 30)
            ),
            'enter_long'] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe['close'] > dataframe['bb_upper']) |
                (dataframe['rsi'] > 70)
            ),
            'exit_long'] = 1
        return dataframe
