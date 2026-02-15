"""
Experimental_Sentiment
Experimental strategy simulating Sentiment Analysis and On-Chain Metrics.
"""

import sys
from pathlib import Path

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import IStrategy


# Add _base to path to allow import
sys.path.append(str(Path(__file__).parent / "_base"))
from AuditedStrategyMixin import AuditedStrategyMixin  # noqa: E402, RUF100


class Experimental_Sentiment(IStrategy, AuditedStrategyMixin):
    INTERFACE_VERSION = 3

    # Minimal ROI
    minimal_roi = {"60": 0.01, "30": 0.02, "0": 0.04}

    # Stoploss
    stoploss = -0.10

    # Timeframe
    timeframe = "1h"

    # Run "populate_indicators" only for new candle
    process_only_new_candles = True

    # These values can be overridden in the "ask_strategy" section in the config.
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    # Number of candles the strategy requires before producing valid signals
    startup_candle_count: int = 100

    # Optional order type mapping.
    order_types = {
        "entry": "limit",
        "exit": "limit",
        "stoploss": "market",
        "stoploss_on_exchange": False,
    }

    # Order time in force.
    order_time_in_force = {"entry": "GTC", "exit": "GTC"}

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Volume Moving Average (24 periods) - Proxy for "Normal Volume"
        dataframe["volume_mean_24"] = ta.SMA(dataframe["volume"], timeperiod=24)

        # Twitter Volume Proxy: Ratio of current volume to 24-period average
        # Logic: Unusually high volume often accompanies social media hype
        dataframe["twitter_volume"] = dataframe["volume"] / dataframe["volume_mean_24"]

        # Whale Movement Proxy: Candle Range (High - Low) / Open
        # Logic: Large price swings relative to open indicate large market participants
        dataframe["whale_movement"] = (dataframe["high"] - dataframe["low"]) / dataframe["open"]

        # Trend Indicator: EMA 50
        dataframe["ema_50"] = ta.EMA(dataframe, timeperiod=50)

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        if not self.check_whitelist(metadata["pair"]):
            return dataframe

        dataframe.loc[
            (
                (dataframe["twitter_volume"] > 2.0)  # High "Social Volume"
                & (dataframe["whale_movement"] > 0.02)  # Large "Whale Move"
                & (dataframe["close"] > dataframe["ema_50"])  # Uptrend
            ),
            "enter_long",
        ] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["twitter_volume"] < 1.0)  # Hype died down
                & (dataframe["close"] < dataframe["ema_50"])  # Trend broken
            ),
            "exit_long",
        ] = 1
        return dataframe

    def confirm_trade_entry(
        self,
        pair: str,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        current_time,
        entry_tag,
        side: str,
        **kwargs,
    ) -> bool:
        """
        Called right before placing a trade.
        """
        self.log_signal(pair, self.timeframe, side, "Signal Confirmed", current_time)
        return True
