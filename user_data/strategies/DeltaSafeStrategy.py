"""
Strategy Name: DeltaSafeStrategy
Author: Unknown
Version: 0.1
Timeframes: 1h

Supported Pair Format:
- Delta futures pairs (BTC/USDT:USDT)
- Adheres to BASE/QUOTE:SETTLE format

Timezone Rule:
- All timestamps logged as UTC ISO-8601

Entry/Exit Definitions:
- Long Entry: RSI < 30 and Volume > 0
- Long Exit: RSI > 70 and Volume > 0
- Short Entry: None
- Short Exit: None

No Repainting:
- Only acts on closed candles.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Any

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

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # RSI
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Check whitelist using Mixin
        if self.config.get("exchange", {}).get("pair_whitelist"):
            if not self.assert_pair_in_whitelist(
                metadata["pair"], self.config["exchange"]["pair_whitelist"]
            ):
                return dataframe

        # Check pair format
        if not self.validate_pair_format(metadata["pair"]):
            return dataframe

        # Named conditions for clarity (Auditor Requirement)
        rsi_oversold = dataframe["rsi"] < 30
        has_volume = dataframe["volume"] > 0

        dataframe.loc[(rsi_oversold & has_volume), "enter_long"] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Named conditions for clarity
        rsi_overbought = dataframe["rsi"] > 70
        has_volume = dataframe["volume"] > 0

        dataframe.loc[(rsi_overbought & has_volume), "exit_long"] = 1
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
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        last_candle = dataframe.iloc[-1].squeeze()

        snapshot = {
            "rsi": last_candle.get("rsi"),
            "volume": last_candle.get("volume"),
            "close": last_candle.get("close"),
        }

        self.log_signal(
            pair=pair,
            side=side,
            reason=entry_tag or "Signal Confirmed",
            ts_utc=last_candle.get("date", current_time),
            indicators_snapshot=snapshot,
        )
        return True

    def confirm_trade_exit(
        self,
        pair: str,
        trade: Any,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        exit_reason: str,
        current_time: datetime,
        **kwargs,
    ) -> bool:
        """
        Called right before exiting a trade.
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        last_candle = dataframe.iloc[-1].squeeze()

        snapshot = {
            "rsi": last_candle.get("rsi"),
            "close": last_candle.get("close"),
            "profit_ratio": trade.calc_profit_ratio(rate) if trade else 0.0,
        }

        self.log_signal(
            pair=pair,
            side="exit",
            reason=exit_reason,
            ts_utc=last_candle.get("date", current_time),
            indicators_snapshot=snapshot,
        )
        return True
