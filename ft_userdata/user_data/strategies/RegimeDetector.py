"""
Market Regime Detector
=======================

System Hypothesis:
    Different market conditions (Bull, Bear, Sideways, High/Low Volatility)
    require different trading strategies. This module detects the current
    regime to adapt strategy parameters dynamically.

Regime Classifications:
    1. Bull Trending: Price > SMA(200) & ADX > 25 & +DI > -DI
    2. Bear Trending: Price < SMA(200) & ADX > 25 & -DI > +DI
    3. Sideways/Range: ADX < 20
    4. High Volatility: ATR > 2x ATR(Daily Average)
    5. Low Volatility: ATR < 0.5x ATR(Daily Average)

Usage:
    Strategies import this module to adjust:
    - Position size (reduce in high volatility)
    - Stop loss width (widen in high volatility)
    - Strategy logic (enable/disable Longs/Shorts)

Author: Elite Trading Strategist
Version: 1.0.0
"""

import talib.abstract as ta
from pandas import DataFrame
import numpy as np


class RegimeDetector:
    @staticmethod
    def detect_regime(dataframe: DataFrame) -> DataFrame:
        """
        Populates dataframe with 'regime' column
        0 = Undefined/Transition
        1 = Bull Trend
        2 = Bear Trend
        3 = Sideways
        """

        # Calculate Trend Indicators
        dataframe["sma_200"] = ta.SMA(dataframe, timeperiod=200)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["plus_di"] = ta.PLUS_DI(dataframe, timeperiod=14)
        dataframe["minus_di"] = ta.MINUS_DI(dataframe, timeperiod=14)

        # Initialize regime column
        dataframe["regime"] = 0

        # 1. Bull Trend
        dataframe.loc[
            (dataframe["close"] > dataframe["sma_200"])
            & (dataframe["adx"] > 25)
            & (dataframe["plus_di"] > dataframe["minus_di"]),
            "regime",
        ] = 1

        # 2. Bear Trend
        dataframe.loc[
            (dataframe["close"] < dataframe["sma_200"])
            & (dataframe["adx"] > 25)
            & (dataframe["minus_di"] > dataframe["plus_di"]),
            "regime",
        ] = 2

        # 3. Sideways
        dataframe.loc[(dataframe["adx"] < 20), "regime"] = 3

        return dataframe

    @staticmethod
    def detect_volatility_state(dataframe: DataFrame) -> DataFrame:
        """
        Populates 'volatility_state' column
        0 = Normal
        1 = High (Risk ON caution)
        2 = Low (Squeeze likely)
        """
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["atr_ma"] = dataframe["atr"].rolling(window=100).mean()

        dataframe["volatility_state"] = 0

        # High Volatility (>1.5x average)
        dataframe.loc[
            dataframe["atr"] > (dataframe["atr_ma"] * 1.5), "volatility_state"
        ] = 1

        # Low Volatility (<0.7x average)
        dataframe.loc[
            dataframe["atr"] < (dataframe["atr_ma"] * 0.7), "volatility_state"
        ] = 2

        return dataframe


# Example usage in strategy:
# dataframe = RegimeDetector.detect_regime(dataframe)
# if regime == 1: enable_long_strategies()
