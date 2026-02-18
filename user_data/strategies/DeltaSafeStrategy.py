from freqtrade.strategy import IStrategy, IntParameter
from pandas import DataFrame
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib
from user_data.strategies._base.AuditedStrategyMixin import AuditedStrategyMixin

class DeltaSafeStrategy(AuditedStrategyMixin, IStrategy):
    INTERFACE_VERSION = 3

    # Minimal ROI
    minimal_roi = {
        "60": 0.01,
        "30": 0.02,
        "0": 0.04
    }

    # Stoploss
    stoploss = -0.10

    # Trailing stop
    trailing_stop = False

    # Timeframe
    timeframe = '5m'

    # Run "populate_indicators" only for new candle
    process_only_new_candles = True

    # Order types
    order_types = {
        'entry': 'limit',
        'exit': 'limit',
        'stoploss': 'market',
        'stoploss_on_exchange': False
    }

    # Example parameter
    buy_rsi = IntParameter(10, 40, default=30, space='buy')
    sell_rsi = IntParameter(60, 90, default=70, space='sell')

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe['rsi'] < self.buy_rsi.value) &
                (dataframe['volume'] > 0)
            ),
            'enter_long'] = 1

        dataframe.loc[
            (
                (dataframe['rsi'] > self.sell_rsi.value) &
                (dataframe['volume'] > 0)
            ),
            'enter_short'] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe['rsi'] > self.sell_rsi.value)
            ),
            'exit_long'] = 1

        dataframe.loc[
            (
                (dataframe['rsi'] < self.buy_rsi.value)
            ),
            'exit_short'] = 1

        return dataframe
