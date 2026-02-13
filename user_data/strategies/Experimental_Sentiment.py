"""
Experimental_Sentiment
A strategy that mocks a sentiment signal (Whale Wallet Movements)
using MFI as a proxy.
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

    # Minimal ROI (same as DeltaSafeStrategy for comparison)
    minimal_roi = {"60": 0.01, "30": 0.02, "0": 0.04}

    # Stoploss (same as DeltaSafeStrategy for comparison)
    stoploss = -0.10

    # Timeframe
    timeframe = "1h"

    # Run "populate_indicators" only for new candle
    process_only_new_candles = True

    # Values can be overridden in "ask_strategy" section in config.
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

    def populate_indicators(
        self, dataframe: DataFrame, metadata: dict
    ) -> DataFrame:
        # RSI
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)

        # MFI (Money Flow Index) - Proxy for Whale Wallet Movements
        # MFI combines price and volume to measure buying and selling pressure.
        # Low MFI (< 20) indicates oversold conditions with volume backing,
        # simulating "smart money" accumulation.
        dataframe["mfi"] = ta.MFI(dataframe, timeperiod=14)

        return dataframe

    def populate_entry_trend(
        self, dataframe: DataFrame, metadata: dict
    ) -> DataFrame:
        if not self.check_whitelist(metadata["pair"]):
            return dataframe

        # Enter Long when RSI < 30 (Oversold) AND MFI < 20
        # (Whale Accumulation Proxy)
        dataframe.loc[
            (
                (dataframe["rsi"] < 30)
                & (dataframe["mfi"] < 20)
                & (dataframe["volume"] > 0)
            ),
            "enter_long",
        ] = 1

        return dataframe

    def populate_exit_trend(
        self, dataframe: DataFrame, metadata: dict
    ) -> DataFrame:
        # Exit Long when RSI > 70 (Overbought)
        dataframe.loc[
            ((dataframe["rsi"] > 70) & (dataframe["volume"] > 0)),
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
        self.log_signal(
            pair,
            self.timeframe,
            side,
            "Signal Confirmed (Sentiment)",
            current_time
        )
        return True
