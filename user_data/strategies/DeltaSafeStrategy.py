"""
DeltaSafeStrategy
A basic strategy for Delta Exchange Futures ensuring compliance with the stack.

# Strategy Name: DeltaSafeStrategy
# Author: Freqtrade
# Version: 1.1
# Supported Timeframes: 1h
# Supported Pair Format: Delta Futures (BTC/USDT:USDT)
# Timezone Rule: UTC ISO-8601
# Entry Conditions: RSI < 30 and Volume > 0
# Exit Conditions: RSI > 70 and Volume > 0
# No Repainting: Only act on closed candles
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import IStrategy

# Add _base to path to allow import
sys.path.append(str(Path(__file__).parent / "_base"))
from AuditedStrategyMixin import AuditedStrategyMixin  # noqa: E402, RUF100


class DeltaSafeStrategy(IStrategy, AuditedStrategyMixin):
    INTERFACE_VERSION = 3

    # Minimal ROI
    minimal_roi = {"60": 0.01, "30": 0.02, "0": 0.04}

    # Stoploss
    stoploss = -0.10

    # Timeframe
    timeframe = "1h"

    # Run "populate_indicators" only for new candle
    # Logic runs on closed candle only
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

    def bot_start(self, **kwargs) -> None:
        """
        Called only once after bot instantiation.
        """
        self.validate_pairs()

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # RSI
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        if not self.assert_pair_in_whitelist(metadata["pair"]):
            return dataframe

        # Thesis: Oversold condition with volume confirmation
        rsi_oversold = dataframe["rsi"] < 30
        volume_exists = dataframe["volume"] > 0

        dataframe.loc[(rsi_oversold & volume_exists), "enter_long"] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Thesis: Overbought condition with volume confirmation
        rsi_overbought = dataframe["rsi"] > 70
        volume_exists = dataframe["volume"] > 0

        dataframe.loc[(rsi_overbought & volume_exists), "exit_long"] = 1
        return dataframe

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
        Called right before placing a trade.
        """
        # Get dataframe to log indicators
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)

        # Helper to safely get value
        indicators = {}
        if not dataframe.empty:
            last_candle = dataframe.iloc[-1].to_dict()
            indicators = {
                "rsi": last_candle.get("rsi"),
                "volume": last_candle.get("volume"),
                "close": last_candle.get("close"),
            }

        # Ensure we use UTC for logging
        if current_time.tzinfo is None:
            ts = current_time.replace(tzinfo=timezone.utc)  # noqa: UP017
        else:
            ts = current_time

        self.log_signal(
            pair=pair,
            side=side,
            reason=entry_tag or "Signal Confirmed",
            ts_utc=ts,
            indicators_snapshot=indicators,
        )
        return True
