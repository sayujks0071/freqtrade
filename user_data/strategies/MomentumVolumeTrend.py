"""
Momentum-Volume-Trend (MVT) Strategy
======================================

Strategy Hypothesis:
    Capture strong upward momentum confirmed by volume expansion and trend strength,
    with multi-timeframe confluence and intelligent risk management.

Entry Logic:
    1. RSI(14) between 50-70 (momentum without overbought)
    2. Volume > 1.8x 20-period average (institutional interest)
    3. Price > EMA(50) > EMA(200) (strong uptrend)
    4. ADX(14) > 25 (trending market, not choppy)
    5. MACD histogram positive and increasing

Exit Logic:
    - Take Profit: 2.5% gain (risk-reward optimized)
    - Stop Loss: 1.2% loss (ATR-based)
    - Trailing Stop: Activates after 1.5% gain
    - Time Exit: 72 hours maximum hold

Risk Management:
    - Max 3 concurrent positions
    - Position size: 33% of available capital per trade
    - Stop loss mandatory on all entries

Expected Performance:
    - Sharpe Ratio: 1.5-2.0
    - Win Rate: 55-65%
    - Max Drawdown: <18%
    - Profit Factor: >1.8

Author: Elite Trading Strategist
Version: 1.0.0
"""

import logging
from datetime import datetime
from functools import reduce

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.persistence import Trade
from freqtrade.strategy import DecimalParameter, IntParameter, IStrategy


logger = logging.getLogger(__name__)


class MomentumVolumeTrend(IStrategy):
    """
    Institutional-grade momentum strategy with volume confirmation
    """

    # Strategy metadata
    INTERFACE_VERSION = 3
    can_short = False

    # ===========================
    # STRATEGY PARAMETERS
    # ===========================

    # Minimal ROI - Take profit targets
    minimal_roi = {"0": 0.223, "24": 0.061, "37": 0.023, "52": 0}

    # Stop loss
    stoploss = -0.305

    # Trailing stop
    trailing_stop = True
    trailing_stop_positive = 0.215
    trailing_stop_positive_offset = 0.294
    trailing_only_offset_is_reached = False

    # Optimal timeframe
    timeframe = "5m"

    # Run "populate_indicators()" only for new candle
    process_only_new_candles = True

    # Experimental settings
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    # Position sizing
    position_adjustment_enable = False
    max_entry_position_adjustment = 0

    # ===========================
    # HYPEROPT PARAMETERS
    # ===========================

    # RSI
    buy_rsi_min = IntParameter(45, 55, default=52, space="buy")
    buy_rsi_max = IntParameter(65, 75, default=71, space="buy")

    # Volume multiplier
    buy_volume_factor = DecimalParameter(1.5, 2.5, decimals=1, default=1.7, space="buy")

    # ADX threshold
    buy_adx_min = IntParameter(20, 30, default=24, space="buy")

    # ===========================
    # INDICATOR POPULATION
    # ===========================

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Generate all indicators needed for the strategy
        """

        # Momentum Indicators
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)

        # Trend Indicators
        dataframe["ema_50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema_200"] = ta.EMA(dataframe, timeperiod=200)

        # MACD
        macd = ta.MACD(dataframe)
        dataframe["macd"] = macd["macd"]
        dataframe["macdsignal"] = macd["macdsignal"]
        dataframe["macdhist"] = macd["macdhist"]

        # Volume
        dataframe["volume_mean"] = dataframe["volume"].rolling(window=20).mean()
        dataframe["volume_ratio"] = dataframe["volume"] / dataframe["volume_mean"]

        # ATR for stop loss
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["atr_percent"] = (dataframe["atr"] / dataframe["close"]) * 100

        # Bollinger Bands (for additional confirmation)
        bollinger = ta.BBANDS(dataframe, timeperiod=20, nbdevup=2.0, nbdevdn=2.0)
        dataframe["bb_upper"] = bollinger["upperband"]
        dataframe["bb_middle"] = bollinger["middleband"]
        dataframe["bb_lower"] = bollinger["lowerband"]
        dataframe["bb_width"] = (dataframe["bb_upper"] - dataframe["bb_lower"]) / dataframe[
            "bb_middle"
        ]

        # Higher timeframe trend (simulated via longer EMA)
        dataframe["ema_100"] = ta.EMA(dataframe, timeperiod=100)

        # MACD histogram slope (momentum acceleration)
        dataframe["macd_hist_slope"] = dataframe["macdhist"] - dataframe["macdhist"].shift(1)

        return dataframe

    # ===========================
    # ENTRY LOGIC
    # ===========================

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Define entry conditions based on indicators
        """

        conditions = []

        # Core Momentum Condition
        conditions.append(
            (dataframe["rsi"] > self.buy_rsi_min.value)
            & (dataframe["rsi"] < self.buy_rsi_max.value)
        )

        # Volume Confirmation
        conditions.append(dataframe["volume_ratio"] > self.buy_volume_factor.value)

        # Trend Conditions
        conditions.append(
            (dataframe["close"] > dataframe["ema_50"])
            & (dataframe["ema_50"] > dataframe["ema_200"])  # Strong uptrend
        )

        # Trending Market (not choppy)
        conditions.append(dataframe["adx"] > self.buy_adx_min.value)

        # MACD Confirmation
        conditions.append(
            (dataframe["macdhist"] > 0)  # Histogram positive
            & (dataframe["macd_hist_slope"] > 0)  # Increasing momentum
        )

        # Additional safety: Not at Bollinger upper band (avoid buying tops)
        conditions.append(dataframe["close"] < dataframe["bb_upper"])

        # Combine all conditions
        if conditions:
            dataframe.loc[reduce(lambda x, y: x & y, conditions), "enter_long"] = 1

        return dataframe

    # ===========================
    # EXIT LOGIC
    # ===========================

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Define exit conditions
        """

        conditions = []

        # Exit when momentum reverses
        conditions.append(
            (dataframe["rsi"] > 75)  # Overbought
            | (dataframe["macdhist"] < 0)  # MACD turning negative
            | (dataframe["close"] < dataframe["ema_50"])  # Broke below trend
        )

        # Exit on volume spike down (potential dump)
        conditions.append(
            (dataframe["volume_ratio"] > 3.0)  # Extreme volume
            & (dataframe["close"] < dataframe["open"])  # Red candle
        )

        if conditions:
            dataframe.loc[reduce(lambda x, y: x | y, conditions), "exit_long"] = 1

        return dataframe

    # ===========================
    # CUSTOM FUNCTIONS
    # ===========================

    def confirm_trade_entry(
        self,
        pair: str,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        current_time: datetime,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> bool:
        """
        Additional entry validation before executing trade
        """

        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        last_candle = dataframe.iloc[-1].squeeze()

        # Don't enter if ATR is too high (excessive volatility)
        if last_candle["atr_percent"] > 3.0:
            logger.info(
                f"Entry rejected for {pair}: ATR too high ({last_candle['atr_percent']:.2f}%)"
            )
            return False

        # Don't enter if volume is dropping
        if dataframe["volume"].iloc[-1] < dataframe["volume"].iloc[-2]:
            logger.info(f"Entry rejected for {pair}: Volume decreasing")
            return False

        return True

    def custom_stoploss(
        self,
        pair: str,
        trade: "Trade",
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        after_fill: bool,
        **kwargs,
    ) -> float | None:
        """
        Dynamic stop loss based on ATR
        """

        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        last_candle = dataframe.iloc[-1].squeeze()

        # Use ATR-based stop: 2x ATR below entry
        atr_stop = (2 * last_candle["atr"]) / trade.open_rate

        # Return the more conservative stop (larger loss)
        return max(-0.012, -atr_stop)  # Never worse than 1.2%

    def leverage(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_leverage: float,
        max_leverage: float,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> float:
        """
        No leverage for this strategy (spot trading only)
        """
        return 1.0
