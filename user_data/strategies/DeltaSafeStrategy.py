"""
Strategy: DeltaSafeStrategy
Author: Jules
Version: 1.1
Timeframe: 1h

Description:
A basic strategy for Delta Exchange Futures ensuring compliance with the stack.

Pair Format:
- Delta futures contracts (e.g. BTCUSDT).
- Must match Freqtrade naming BASE/QUOTE:SETTLE (e.g. BTC/USDT:USDT).

Timezone:
- All timestamps logs are UTC ISO-8601.

Entry/Exit:
- Long Entry: RSI < 30 and Volume > 0
- Long Exit: RSI > 70 and Volume > 0
- Short Entry: None
- Short Exit: None

Repainting:
- Logic must strictly run on closed candles. No look-ahead or repainting.
"""

from __future__ import annotations

import sys
from pathlib import Path
from datetime import datetime

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
        # Sanity check for pair format
        self.validate_pair_format(metadata["pair"])

        # RSI
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Check whitelist if available in config
        whitelist = self.config.get("exchange", {}).get("pair_whitelist")
        if whitelist:
            try:
                self.assert_pair_in_whitelist(metadata["pair"], whitelist)
            except ValueError:
                return dataframe

        # Named boolean conditions
        rsi_oversold = dataframe["rsi"] < 30
        volume_ok = dataframe["volume"] > 0

        dataframe.loc[rsi_oversold & volume_ok, "enter_long"] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Named boolean conditions
        rsi_overbought = dataframe["rsi"] > 70
        volume_ok = dataframe["volume"] > 0

        dataframe.loc[rsi_overbought & volume_ok, "exit_long"] = 1

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
        indicators = {}
        if self.dp:
            # Get latest candle
            try:
                df = self.dp.get_pair_dataframe(pair, self.timeframe)
                if not df.empty:
                    last_row = df.iloc[-1]
                    indicators = {
                        "rsi": last_row.get("rsi"),
                        "volume": last_row.get("volume"),
                        "close": last_row.get("close"),
                    }
            except Exception:
                # Fallback if DP not available or fails
                pass

        self.log_signal(
            pair=pair,
            side=side,
            reason=entry_tag or "Signal Confirmed",
            ts_utc=current_time,
            indicators=indicators,
        )
        return True
