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
    minimal_roi = {"0": 0.2, "30": 0.05, "60": 0.02}
    stoploss = -0.10
    timeframe = "1h"
    process_only_new_candles = True
    startup_candle_count = 200

    # Enable Shorting
    can_short = True

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe['ema200'] = ta.EMA(dataframe, timeperiod=200)
        dataframe['high_10'] = dataframe['high'].rolling(10).max()
        dataframe['low_20'] = dataframe['low'].rolling(20).min()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        if not self.check_whitelist(metadata['pair']):
            return dataframe

        # Short Entry: Price below EMA200 (Downtrend) AND Breakdown below 20-period Low
        dataframe.loc[
            (
                (dataframe['close'] < dataframe['ema200']) &
                (dataframe['close'] < dataframe['low_20'])
            ),
            'enter_short'] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Exit Short: Price breaks above recent 10-period High
        dataframe.loc[
            (dataframe['close'] > dataframe['high_10']),
            'exit_short'] = 1
        return dataframe
