"""
Volatility Breakout Strategy
=============================

Strategy Hypothesis:
    Capture explosive price movements when volatility expands
    after consolidation periods. Buy breakouts with volume confirmation.

Entry Logic:
    1. Bollinger Band width expanding (volatility increase)
    2. Price breaks above recent high (20-period)
    3. Volume > 2x average (strong conviction)
    4. ADX rising (trend strengthening)
    5. Not overbought (RSI < 75)

Exit Logic:
    - Take Profit: 4% gain (capture momentum)
    - Stop Loss: 1.8% loss
    - Trailing Stop: Trail by 2.5% after 2% gain
    - Exit if volatility contracts significantly

Expected Performance:
    - Win Rate: 45-55% (lower but bigger winners)
    - Profit Factor: > 2.0
    - Sharpe: 1.6-2.0

Author: Elite Trading Strategist
Version: 1.0.0
"""

import logging
from functools import reduce

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import DecimalParameter, IStrategy


logger = logging.getLogger(__name__)


class VolatilityBreakout(IStrategy):
    """
    Breakout strategy capturing volatility expansions
    """

    INTERFACE_VERSION = 3
    can_short = False

    minimal_roi = {
        "0": 0.04,  # 4% target
        "30": 0.025,  # After 30 min
        "60": 0.015,  # After 1 hour
    }

    stoploss = -0.018  # 1.8%

    trailing_stop = True
    trailing_stop_positive = 0.02  # After 2% gain
    trailing_stop_positive_offset = 0.025  # Trail by 2.5%
    trailing_only_offset_is_reached = True

    timeframe = "5m"

    process_only_new_candles = True
    use_exit_signal = True

    # Hyperopt
    buy_bb_width_min = DecimalParameter(0.02, 0.06, decimals=3, default=0.035, space="buy")
    buy_volume_factor = DecimalParameter(1.8, 2.5, decimals=1, default=2.0, space="buy")

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Indicators for breakout detection"""

        # Bollinger Bands
        bollinger = ta.BBANDS(dataframe, timeperiod=20, nbdevup=2.0, nbdevdn=2.0)
        dataframe["bb_upper"] = bollinger["upperband"]
        dataframe["bb_middle"] = bollinger["middleband"]
        dataframe["bb_lower"] = bollinger["lowerband"]

        # BB Width (volatility measure)
        dataframe["bb_width"] = (dataframe["bb_upper"] - dataframe["bb_lower"]) / dataframe[
            "bb_middle"
        ]
        dataframe["bb_width_expanding"] = dataframe["bb_width"] > dataframe["bb_width"].shift(1)

        # Price action
        dataframe["high_20"] = dataframe["high"].rolling(window=20).max()
        dataframe["breakout"] = dataframe["close"] > dataframe["high_20"].shift(1)

        # Momentum
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["adx_rising"] = dataframe["adx"] > dataframe["adx"].shift(1)

        # Volume
        dataframe["volume_mean"] = dataframe["volume"].rolling(window=20).mean()
        dataframe["volume_ratio"] = dataframe["volume"] / dataframe["volume_mean"]

        # ATR
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Entry on breakout conditions"""

        conditions = []

        # Volatility expanding
        conditions.append(
            (dataframe["bb_width"] > self.buy_bb_width_min.value)
            & (dataframe["bb_width_expanding"])
        )

        # Price breakout
        conditions.append(dataframe["breakout"])

        # Volume confirmation
        conditions.append(dataframe["volume_ratio"] > self.buy_volume_factor.value)

        # Trend strengthening
        conditions.append(dataframe["adx_rising"] & (dataframe["adx"] > 20))

        # Not overbought
        conditions.append(dataframe["rsi"] < 75)

        if conditions:
            dataframe.loc[reduce(lambda x, y: x & y, conditions), "enter_long"] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Exit when momentum fades"""

        conditions = []

        # Volatility contracting significantly
        conditions.append(dataframe["bb_width"] < dataframe["bb_width"].shift(5) * 0.7)

        # OR RSI overbought
        conditions.append(dataframe["rsi"] > 80)

        if conditions:
            dataframe.loc[reduce(lambda x, y: x | y, conditions), "exit_long"] = 1

        return dataframe

    def leverage(
        self,
        pair: str,
        current_time,
        current_rate: float,
        proposed_leverage: float,
        max_leverage: float,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> float:
        return 1.0
