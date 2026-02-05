import sys
from pathlib import Path

# Add _base to path to allow importing mixin
sys.path.append(str(Path(__file__).parent / "_base"))

from freqtrade.strategy import IStrategy
from pandas import DataFrame
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib

# noqa: E402
from AuditedStrategyMixin import AuditedStrategyMixin  # noqa: E402


class DeltaSafeStrategy(IStrategy, AuditedStrategyMixin):
    """
    Sample strategy for Delta Exchange using AuditedStrategyMixin.

    Metadata:
    Strategy: DeltaSafeStrategy
    Author: Jules
    Version: 1.0
    Timeframe: 5m
    Pair Format: BASE/QUOTE:SETTLE
    Timezone: UTC
    Entry/Exit: RSI + Macd
    Repainting: No
    """

    INTERFACE_VERSION = 3
    timeframe = "5m"

    # ROI table:
    minimal_roi = {"60": 0.01, "30": 0.02, "0": 0.04}

    stoploss = -0.10

    # Trailing stoploss
    trailing_stop = False

    process_only_new_candles = True
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    startup_candle_count = 30

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)

        macd = ta.MACD(dataframe)
        dataframe["macd"] = macd["macd"]
        dataframe["macdsignal"] = macd["macdsignal"]

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            ((dataframe["rsi"] < 30) & (dataframe["macd"] > dataframe["macdsignal"])),
            "enter_long",
        ] = 1

        dataframe.loc[
            ((dataframe["rsi"] > 70) & (dataframe["macd"] < dataframe["macdsignal"])),
            "enter_short",
        ] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[(dataframe["rsi"] > 70), "exit_long"] = 1

        dataframe.loc[(dataframe["rsi"] < 30), "exit_short"] = 1

        return dataframe
