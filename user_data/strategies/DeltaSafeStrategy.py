"""
DeltaSafeStrategy
A basic strategy for Delta Exchange Futures ensuring compliance with the stack.
"""

import sys
from datetime import datetime
from pathlib import Path


# Add _base to path to allow import
sys.path.append(str(Path(__file__).parent / "_base"))

import talib.abstract as ta
from AuditedStrategyMixin import AuditedStrategyMixin
from pandas import DataFrame

from freqtrade.strategy import IStrategy


class DeltaSafeStrategy(IStrategy, AuditedStrategyMixin):
    """
    # Strategy Audit Header
    # ---------------------
    # Strategy Name: DeltaSafeStrategy
    # Author: Freqtrade User
    # Version: 1.1
    # Supported Timeframes: 1h
    #
    # Pair Format Notes:
    # - Delta Contract: e.g., BTCUSDT
    # - Freqtrade Pair: e.g., BTC/USDT:USDT
    #
    # Timezone Rule:
    # - All timestamps logged as UTC ISO-8601
    #
    # Entry/Exit Definitions:
    # - Long Entry: RSI < 30 and Volume > 0
    # - Long Exit: RSI > 70 and Volume > 0
    # - Short Entry: N/A
    # - Short Exit: N/A
    #
    # Repainting Note:
    # - Only act on closed candles (no incomplete candle usage)
    # ---------------------
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

    def bot_start(self, **kwargs) -> None:
        """
        Called only once after bot instantiation.
        """
        if self.dp:
            for pair in self.dp.current_whitelist():
                self.normalize_pair(pair)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # RSI
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Use assert_pair_in_whitelist from mixin
        if self.config.get("exchange", {}).get("pair_whitelist"):
            if not self.assert_pair_in_whitelist(
                metadata["pair"], self.config["exchange"]["pair_whitelist"]
            ):
                return dataframe

        # Named boolean conditions for clarity and audit
        is_oversold = dataframe["rsi"] < 30
        has_volume = dataframe["volume"] > 0

        dataframe.loc[(is_oversold & has_volume), "enter_long"] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Named boolean conditions
        is_overbought = dataframe["rsi"] > 70
        has_volume = dataframe["volume"] > 0

        dataframe.loc[(is_overbought & has_volume), "exit_long"] = 1
        return dataframe

    def confirm_trade_entry(
        self,
        pair: str,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        current_time: datetime,
        entry_tag,
        side: str,
        **kwargs,
    ) -> bool:
        """
        Called right before placing a trade.
        """
        indicators = {}
        if self.dp:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            if not dataframe.empty:
                last_candle = dataframe.iloc[-1]
                indicators = {
                    "rsi": last_candle.get("rsi"),
                    "volume": last_candle.get("volume"),
                    "close": last_candle.get("close"),
                }

        reason = f"Entry {side} signal"
        self.log_signal(pair, side, reason, current_time, indicators)
        return True

    def confirm_trade_exit(
        self,
        pair: str,
        trade,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        exit_reason: str,
        current_time: datetime,
        **kwargs,
    ) -> bool:
        indicators = {}
        if self.dp:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            if not dataframe.empty:
                last_candle = dataframe.iloc[-1]
                indicators = {
                    "rsi": last_candle.get("rsi"),
                    "volume": last_candle.get("volume"),
                    "close": last_candle.get("close"),
                }

        # side is opposite of trade.trade_direction if we are exiting?
        # trade object has 'trade_direction' (long/short)
        # but here we log the action "exit_long" or "exit_short"
        side = f"exit_{trade.trade_direction}"

        self.log_signal(pair, side, exit_reason, current_time, indicators)
        return True
