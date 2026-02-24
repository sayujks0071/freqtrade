import sys
from pathlib import Path

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import IStrategy


# Add _base to path to allow import
sys.path.append(str(Path(__file__).parent / "_base"))
from AuditedStrategyMixin import AuditedStrategyMixin


class MomentumVolumeTrend(IStrategy, AuditedStrategyMixin):
    INTERFACE_VERSION = 3
    minimal_roi = {"0": 0.1, "30": 0.05, "60": 0.01}
    stoploss = -0.10
    timeframe = "1h"
    process_only_new_candles = True
    startup_candle_count = 200

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe['ema200'] = ta.EMA(dataframe, timeperiod=200)
        dataframe['ema20'] = ta.EMA(dataframe, timeperiod=20)
        dataframe['adx'] = ta.ADX(dataframe)
        # Calculate volume SMA using the volume column directly
        dataframe['volume_sma'] = ta.SMA(dataframe['volume'], timeperiod=20)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        if not self.check_whitelist(metadata['pair']):
            return dataframe

        dataframe.loc[
            (
                (dataframe['close'] > dataframe['ema200']) &
                (dataframe['adx'] > 25) &
                (dataframe['volume'] > dataframe['volume_sma'])
            ),
            'enter_long'] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe['close'] < dataframe['ema20']),
            'exit_long'] = 1
        return dataframe
