"""
Experimental_Sentiment
A strategy that mocks external sentiment signals like "Twitter Volume" and "Whale Wallet Movements".
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

    # Number of candles the strategy requires before producing valid signals
    startup_candle_count: int = 30

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
        # RSI
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)

        # MOCK SIGNAL: Twitter Volume
        # Simulating "Twitter Volume" using Volume Ratio (current volume / 24h avg volume)
        # In a real scenario, this would be an external API call or merged dataframe
        dataframe["volume_mean_24"] = dataframe["volume"].rolling(24).mean()
        dataframe["twitter_volume"] = dataframe["volume"] / dataframe["volume_mean_24"]

        # MOCK SIGNAL: Whale Wallet Movements
        # Simulating "Whale Movements" using large price candles (High - Low) / Open
        # This assumes large price movements are driven by whales
        dataframe["whale_movement"] = (dataframe["high"] - dataframe["low"]) / dataframe["open"]

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        if not self.check_whitelist(metadata["pair"]):
            return dataframe

        # Entry Long:
        # 1. High "Twitter Volume" (> 1.5x average) - Hype/Fear
        # 2. Significant "Whale Movement" (> 1.5%) - Smart money moving
        # 3. RSI < 30 - Oversold condition (Whales buying the dip)
        dataframe.loc[
            (
                (dataframe["twitter_volume"] > 1.5)
                & (dataframe["whale_movement"] > 0.015)
                & (dataframe["rsi"] < 30)
                & (dataframe["volume"] > 0)
            ),
            "enter_long",
        ] = 1

        # Entry Short:
        # 1. High "Twitter Volume" (> 1.5x average)
        # 2. Significant "Whale Movement" (> 1.5%)
        # 3. RSI > 70 - Overbought condition (Whales dumping)
        dataframe.loc[
            (
                (dataframe["twitter_volume"] > 1.5)
                & (dataframe["whale_movement"] > 0.015)
                & (dataframe["rsi"] > 70)
                & (dataframe["volume"] > 0)
            ),
            "enter_short",
        ] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Exit Long:
        # RSI > 70 (Overbought) OR "Twitter Volume" drops (Interest lost)
        # Using a simplified exit for now: RSI > 70
        dataframe.loc[((dataframe["rsi"] > 70) & (dataframe["volume"] > 0)), "exit_long"] = 1

        # Exit Short:
        # RSI < 30 (Oversold)
        dataframe.loc[((dataframe["rsi"] < 30) & (dataframe["volume"] > 0)), "exit_short"] = 1

        return dataframe
