"""
Experimental_Sentiment
A strategy incorporating simulated "Whale Wallet Movements" using MFI.
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
        # RSI (from DeltaSafe)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)

        # MFI (Simulated "Whale Wallet Movements")
        # MFI uses price and volume to measure buying/selling pressure.
        # Low MFI (< 20) suggests oversold conditions (Whales accumulating?)
        dataframe["whale_movement"] = ta.MFI(dataframe, timeperiod=14)

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        if not self.check_whitelist(metadata["pair"]):
            return dataframe

        # Entry logic:
        # RSI < 30 (Oversold) AND
        # Whale Movement < 20 (Strong accumulation/oversold volume)
        dataframe.loc[
            (
                (dataframe["rsi"] < 30)
                & (dataframe["whale_movement"] < 20)
                & (dataframe["volume"] > 0)
            ),
            "enter_long",
        ] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Exit logic:
        # RSI > 70 (Overbought) OR
        # Whale Movement > 80 (Whale distribution?)
        dataframe.loc[
            (
                ((dataframe["rsi"] > 70) | (dataframe["whale_movement"] > 80))
                & (dataframe["volume"] > 0)
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
