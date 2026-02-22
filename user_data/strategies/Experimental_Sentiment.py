"""
Experimental_Sentiment
Strategy attempting to find alpha using mocked sentiment signals.
"""

import logging
import sys
from pathlib import Path

import numpy as np
import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import IntParameter, IStrategy


# Add _base to path to allow import
sys.path.append(str(Path(__file__).parent / "_base"))
from AuditedStrategyMixin import AuditedStrategyMixin  # noqa: E402, RUF100


logger = logging.getLogger(__name__)


class Experimental_Sentiment(IStrategy, AuditedStrategyMixin):
    """
    Experimental strategy using mocked sentiment analysis.
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

    # These values can be overridden in the "ask_strategy" section in the config.
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

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

    # Hyperoptable parameters
    buy_rsi = IntParameter(10, 40, default=30, space="buy")
    sell_rsi = IntParameter(60, 90, default=70, space="sell")

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # RSI
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)

        # MOCK SIGNAL: "Whale Wallet Movements"
        # Logic: High Volume but Low Price Range (Accumulation)
        # We define "whale_accumulation" as Volume / (High - Low)
        # Add epsilon to avoid division by zero
        range_eps = 0.00001
        dataframe["price_range"] = dataframe["high"] - dataframe["low"]
        dataframe["whale_accumulation"] = dataframe["volume"] / (
            dataframe["price_range"] + range_eps
        )

        # Normalize whale_accumulation using rolling mean/std to create a z-score or ratio
        dataframe["whale_accumulation_mean"] = (
            dataframe["whale_accumulation"].rolling(window=20).mean()
        )
        dataframe["whale_accumulation_std"] = (
            dataframe["whale_accumulation"].rolling(window=20).std()
        )

        # MOCK SIGNAL: "Twitter Volume"
        # Logic: High Volatility often correlates with high social media chatter.
        # We use Price Volatility (Standard Deviation of returns) as a proxy.
        dataframe["twitter_hype"] = dataframe["close"].pct_change().rolling(window=5).std()
        dataframe["twitter_hype_mean"] = dataframe["twitter_hype"].rolling(window=20).mean()

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        if not self.check_whitelist(metadata["pair"]):
            return dataframe

        # Entry Logic:
        # 1. Whale Accumulation is HIGH (Whale is buying without moving price much)
        # 2. RSI is LOW (Oversold)
        # 3. Twitter Hype is LOW (No one is talking about it yet - contrarian)

        conditions = []
        conditions.append(dataframe["rsi"] < self.buy_rsi.value)

        # Ensure we have data for accumulation (avoid NaN from startup)
        # Using a simpler condition for accumulation: Current accumulation > Mean + 1 StdDev
        conditions.append(
            dataframe["whale_accumulation"]
            > (dataframe["whale_accumulation_mean"] + dataframe["whale_accumulation_std"])
        )

        # Contrarian: Buy when hype is low
        conditions.append(dataframe["twitter_hype"] < dataframe["twitter_hype_mean"])

        conditions.append(dataframe["volume"] > 0)

        if conditions:
            dataframe.loc[(np.bitwise_and.reduce(conditions)), "enter_long"] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Exit Logic:
        # 1. RSI is HIGH (Overbought)

        conditions = []
        conditions.append(dataframe["rsi"] > self.sell_rsi.value)
        conditions.append(dataframe["volume"] > 0)

        if conditions:
            dataframe.loc[
                (dataframe["rsi"] > self.sell_rsi.value) & (dataframe["volume"] > 0), "exit_long"
            ] = 1

        return dataframe
