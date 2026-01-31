# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
# flake8: noqa: F401
# isort: skip_file
# --- Do not remove these imports ---
import numpy as np
import pandas as pd
from datetime import datetime, timedelta, timezone
from pandas import DataFrame
from typing import Optional, Union

from freqtrade.strategy import (
    IStrategy,
    Trade,
    Order,
    PairLocks,
    informative,  # @informative decorator
    # Hyperopt Parameters
    BooleanParameter,
    CategoricalParameter,
    DecimalParameter,
    IntParameter,
    RealParameter,
    # timeframe helpers
    timeframe_to_minutes,
    timeframe_to_next_date,
    timeframe_to_prev_date,
    # Strategy helper functions
    merge_informative_pair,
    stoploss_from_absolute,
    stoploss_from_open,
)

# --------------------------------
# Add your lib to import here
import talib.abstract as ta
from technical import qtpylib
from user_data.strategies._base.AuditedStrategyMixin import AuditedStrategyMixin

# This class is a sample. Feel free to customize it.
class SampleStrategy(IStrategy, AuditedStrategyMixin):
    """
    Strategy Name: SampleStrategy
    Author: Freqtrade + Audited by Google Jules
    Version: 1.1
    Supported Timeframes: 5m
    Supported Pair format: Freqtrade Standard (Base/Quote:Settle) or Delta (BaseQuote)
    Timezone: UTC (timestamps logged as UTC ISO-8601)

    Entry Conditions:
        Long: RSI crosses above buy_rsi, TEMA <= BB Middle, TEMA raising, Volume > 0
        Short: RSI crosses above short_rsi, TEMA > BB Middle, TEMA falling, Volume > 0

    Exit Conditions:
        Long: RSI crosses above sell_rsi, TEMA > BB Middle, TEMA falling, Volume > 0
        Short: RSI crosses above exit_short_rsi, TEMA <= BB Middle, TEMA raising, Volume > 0

    No Repainting: This strategy only acts on closed candles.
    """

    # Strategy interface version - allow new iterations of the strategy interface.
    # Check the documentation or the Sample strategy to get the latest version.
    INTERFACE_VERSION = 3

    # Can this strategy go short?
    can_short: bool = False

    # Minimal ROI designed for the strategy.
    # This attribute will be overridden if the config file contains "minimal_roi".
    minimal_roi = {
        # "120": 0.0,  # exit after 120 minutes at break even
        "60": 0.01,
        "30": 0.02,
        "0": 0.04,
    }

    # Optimal stoploss designed for the strategy.
    # This attribute will be overridden if the config file contains "stoploss".
    stoploss = -0.10

    # Trailing stoploss
    trailing_stop = False
    # trailing_only_offset_is_reached = False
    # trailing_stop_positive = 0.01
    # trailing_stop_positive_offset = 0.0  # Disabled / not configured

    # Optimal timeframe for the strategy.
    timeframe = "5m"

    # Run "populate_indicators()" only for new candle.
    process_only_new_candles = True

    # These values can be overridden in the config.
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    # Hyperoptable parameters
    buy_rsi = IntParameter(low=1, high=50, default=30, space="buy", optimize=True, load=True)
    sell_rsi = IntParameter(low=50, high=100, default=70, space="sell", optimize=True, load=True)
    short_rsi = IntParameter(low=51, high=100, default=70, space="sell", optimize=True, load=True)
    exit_short_rsi = IntParameter(
        low=1, high=50, default=30, space="exit", optimize=True, load=True
    )

    # Number of candles the strategy requires before producing valid signals
    startup_candle_count: int = 200

    # Optional order type mapping.
    order_types = {
        "entry": "limit",
        "exit": "limit",
        "stoploss": "market",
        "stoploss_on_exchange": False,
    }

    # Optional order time in force.
    order_time_in_force = {"entry": "GTC", "exit": "GTC"}

    plot_config = {
        "main_plot": {
            "tema": {},
            "sar": {"color": "white"},
        },
        "subplots": {
            "MACD": {
                "macd": {"color": "blue"},
                "macdsignal": {"color": "orange"},
            },
            "RSI": {
                "rsi": {"color": "red"},
            },
        },
    }

    def informative_pairs(self):
        return []

    def bot_start(self, **kwargs) -> None:
        """
        Called only once after bot instantiation.
        """
        if self.config.get('exchange', {}).get('pair_whitelist'):
            for pair in self.config['exchange']['pair_whitelist']:
                self.normalize_pair(pair)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Momentum Indicators
        dataframe["adx"] = ta.ADX(dataframe)
        dataframe["rsi"] = ta.RSI(dataframe)

        # Stochastic Fast
        stoch_fast = ta.STOCHF(dataframe)
        dataframe["fastd"] = stoch_fast["fastd"]
        dataframe["fastk"] = stoch_fast["fastk"]

        # MACD
        macd = ta.MACD(dataframe)
        dataframe["macd"] = macd["macd"]
        dataframe["macdsignal"] = macd["macdsignal"]
        dataframe["macdhist"] = macd["macdhist"]

        # MFI
        dataframe["mfi"] = ta.MFI(dataframe)

        # Bollinger Bands
        bollinger = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=2)
        dataframe["bb_lowerband"] = bollinger["lower"]
        dataframe["bb_middleband"] = bollinger["mid"]
        dataframe["bb_upperband"] = bollinger["upper"]
        dataframe["bb_percent"] = (dataframe["close"] - dataframe["bb_lowerband"]) / (
            dataframe["bb_upperband"] - dataframe["bb_lowerband"]
        )
        dataframe["bb_width"] = (dataframe["bb_upperband"] - dataframe["bb_lowerband"]) / dataframe[
            "bb_middleband"
        ]

        # Parabolic SAR
        dataframe["sar"] = ta.SAR(dataframe)

        # TEMA - Triple Exponential Moving Average
        dataframe["tema"] = ta.TEMA(dataframe, timeperiod=9)

        # Cycle Indicator
        hilbert = ta.HT_SINE(dataframe)
        dataframe["htsine"] = hilbert["sine"]
        dataframe["htleadsine"] = hilbert["leadsine"]

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Based on TA indicators, populates the entry signal for the given dataframe
        """

        # Long Conditions
        long_rsi_cond = qtpylib.crossed_above(dataframe["rsi"], self.buy_rsi.value)
        long_tema_low_cond = dataframe["tema"] <= dataframe["bb_middleband"]
        long_tema_raise_cond = dataframe["tema"] > dataframe["tema"].shift(1)
        volume_cond = dataframe["volume"] > 0

        enter_long_cond = (
            long_rsi_cond
            & long_tema_low_cond
            & long_tema_raise_cond
            & volume_cond
        )
        dataframe.loc[enter_long_cond, "enter_long"] = 1

        # Short Conditions
        short_rsi_cond = qtpylib.crossed_above(dataframe["rsi"], self.short_rsi.value)
        short_tema_high_cond = dataframe["tema"] > dataframe["bb_middleband"]
        short_tema_fall_cond = dataframe["tema"] < dataframe["tema"].shift(1)

        enter_short_cond = (
            short_rsi_cond
            & short_tema_high_cond
            & short_tema_fall_cond
            & volume_cond
        )
        dataframe.loc[enter_short_cond, "enter_short"] = 1

        # Audit Logging
        if self.is_live_or_dry() and not dataframe.empty:
            last_row = dataframe.iloc[-1]
            ts = last_row.get('date', datetime.now(timezone.utc))

            if last_row.get('enter_long') == 1:
                reason = "RSI crossed above buy_rsi & TEMA <= BB Mid & TEMA raising"
                snapshot = {
                    'rsi': last_row['rsi'],
                    'tema': last_row['tema'],
                    'bb_middleband': last_row['bb_middleband'],
                    'buy_rsi': self.buy_rsi.value
                }
                self.log_signal(metadata['pair'], 'long', reason, ts, snapshot)

            if last_row.get('enter_short') == 1:
                reason = "RSI crossed above short_rsi & TEMA > BB Mid & TEMA falling"
                snapshot = {
                    'rsi': last_row['rsi'],
                    'tema': last_row['tema'],
                    'bb_middleband': last_row['bb_middleband'],
                    'short_rsi': self.short_rsi.value
                }
                self.log_signal(metadata['pair'], 'short', reason, ts, snapshot)

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Based on TA indicators, populates the exit signal for the given dataframe
        """

        # Long Exit
        exit_long_rsi_cond = qtpylib.crossed_above(dataframe["rsi"], self.sell_rsi.value)
        exit_long_tema_cond = dataframe["tema"] > dataframe["bb_middleband"]
        exit_long_tema_fall = dataframe["tema"] < dataframe["tema"].shift(1)
        volume_cond = dataframe["volume"] > 0

        exit_long_cond = (
            exit_long_rsi_cond
            & exit_long_tema_cond
            & exit_long_tema_fall
            & volume_cond
        )
        dataframe.loc[exit_long_cond, "exit_long"] = 1

        # Short Exit
        exit_short_rsi_cond = qtpylib.crossed_above(dataframe["rsi"], self.exit_short_rsi.value)
        exit_short_tema_cond = dataframe["tema"] <= dataframe["bb_middleband"]
        exit_short_tema_raise = dataframe["tema"] > dataframe["tema"].shift(1)

        exit_short_cond = (
            exit_short_rsi_cond
            & exit_short_tema_cond
            & exit_short_tema_raise
            & volume_cond
        )
        dataframe.loc[exit_short_cond, "exit_short"] = 1

        # Audit Logging
        if self.is_live_or_dry() and not dataframe.empty:
            last_row = dataframe.iloc[-1]
            ts = last_row.get('date', datetime.now(timezone.utc))

            if last_row.get('exit_long') == 1:
                reason = "RSI crossed above sell_rsi & TEMA > BB Mid & TEMA falling"
                snapshot = {
                    'rsi': last_row['rsi'],
                    'tema': last_row['tema'],
                    'bb_middleband': last_row['bb_middleband'],
                    'sell_rsi': self.sell_rsi.value
                }
                self.log_signal(metadata['pair'], 'exit_long', reason, ts, snapshot)

            if last_row.get('exit_short') == 1:
                reason = "RSI crossed above exit_short_rsi & TEMA <= BB Mid & TEMA raising"
                snapshot = {
                    'rsi': last_row['rsi'],
                    'tema': last_row['tema'],
                    'bb_middleband': last_row['bb_middleband'],
                    'exit_short_rsi': self.exit_short_rsi.value
                }
                self.log_signal(metadata['pair'], 'exit_short', reason, ts, snapshot)

        return dataframe
