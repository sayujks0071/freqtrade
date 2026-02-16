
import sys
from pathlib import Path

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import IStrategy


# Add _base to path to allow import
sys.path.append(str(Path(__file__).parent / "_base"))
from AuditedStrategyMixin import AuditedStrategyMixin  # noqa: E402, RUF100


class Experimental_Sentiment(IStrategy, AuditedStrategyMixin):
    """
    Experimental strategy that mocks sentiment analysis using on-chain metrics proxies.
    """

    INTERFACE_VERSION = 3

    # Minimal ROI
    minimal_roi = {"60": 0.01, "30": 0.02, "0": 0.04}

    # Stoploss
    stoploss = -0.10

    # Timeframe
    timeframe = "1h"

    # Run "populate_indicators" only for new candle
    process_only_new_candles = True

    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    # Number of candles the strategy requires before producing valid signals
    startup_candle_count: int = 30

    order_types = {
        "entry": "limit",
        "exit": "limit",
        "stoploss": "market",
        "stoploss_on_exchange": False,
    }

    order_time_in_force = {"entry": "GTC", "exit": "GTC"}

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # RSI
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)

        # Mock Signal 1: "Twitter Volume" (Relative Volume)
        # Proxy: Volume / 24-period SMA of Volume
        dataframe["volume_sma"] = ta.SMA(dataframe["volume"], timeperiod=24)
        dataframe["twitter_volume"] = dataframe["volume"] / dataframe["volume_sma"]

        # Mock Signal 2: "Whale Wallet Movements" (Large Transactions / Volatility)
        # Proxy: (High - Low) / Open (Normalized Range)
        dataframe["whale_movement"] = (dataframe["high"] - dataframe["low"]) / dataframe["open"]

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["twitter_volume"] > 1.5)  # High social buzz (volume spike)
                & (dataframe["whale_movement"] > 0.02)  # Large movements
                & (dataframe["rsi"] < 30)  # Oversold condition
                & (dataframe["volume"] > 0)
            ),
            "enter_long",
        ] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["rsi"] > 70)  # Overbought
                & (dataframe["volume"] > 0)
            ),
            "exit_long",
        ] = 1
        return dataframe
