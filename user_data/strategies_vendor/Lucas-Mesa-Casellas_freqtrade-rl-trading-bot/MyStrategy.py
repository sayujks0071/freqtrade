import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import IntParameter
from freqtrade.strategy.interface import IStrategy


class MyStrategy(IStrategy):
    timeframe = "5m"

    # Hyperoptable buy parameters
    ema_period = IntParameter(20, 100, default=50, space="buy")
    rsi_buy = IntParameter(10, 40, default=30, space="buy")
    macd_fast = IntParameter(8, 15, default=12, space="buy")
    macd_slow = IntParameter(20, 30, default=26, space="buy")
    macd_signal = IntParameter(5, 12, default=9, space="buy")

    # ROI and Stoploss from previous best
    minimal_roi = {"0": 0.149, "27": 0.049, "50": 0.036, "92": 0}

    stoploss = -0.338
    trailing_stop = False

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["ema"] = ta.EMA(dataframe, timeperiod=self.ema_period.value)

        macd = ta.MACD(
            dataframe,
            fastperiod=self.macd_fast.value,
            slowperiod=self.macd_slow.value,
            signalperiod=self.macd_signal.value,
        )
        dataframe["macd"] = macd["macd"]
        dataframe["macdsignal"] = macd["macdsignal"]
        dataframe["macdhist"] = macd["macdhist"]

        return dataframe

    def populate_buy_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["rsi"] < self.rsi_buy.value)
                & (dataframe["close"] < dataframe["ema"])
                & (dataframe["macd"] > dataframe["macdsignal"])
                & (dataframe["volume"] > 0)
            ),
            "buy",
        ] = 1
        return dataframe

    def populate_sell_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[(dataframe["rsi"] > 70), "sell"] = 1
        return dataframe
