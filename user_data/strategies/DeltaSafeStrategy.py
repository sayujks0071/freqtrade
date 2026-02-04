"""
Strategy Name: DeltaSafeStrategy
Author: Google Jules
Version: 1.1
Supported Timeframes: 1h

Supported Pair Format:
- Delta Contract: BTCUSDT
- Freqtrade Pair: BTC/USDT:USDT

Timezone Rule:
- All timestamps must be UTC ISO-8601.

Entry/Exit Definitions:
- Long Entry: RSI < 30 and Volume > 0
- Long Exit: RSI > 70 and Volume > 0
- Short Entry: None
- Short Exit: None

No Repainting:
- Logic must strictly rely on closed candles (process_only_new_candles=True).
"""

import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy


# Add _base to path to allow import
sys.path.append(str(Path(__file__).parent / "_base"))
from AuditedStrategyMixin import AuditedStrategyMixin


class DeltaSafeStrategy(IStrategy, AuditedStrategyMixin):
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

    def check_symbol_sanity(self, pair: str):
        """
        Fail fast if pair format mismatches futures naming.
        Expected: BASE/QUOTE:SETTLE
        """
        if ":" not in pair or "/" not in pair:
            raise ValueError(f"Pair {pair} does not match Futures format (BASE/QUOTE:SETTLE)")

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Sanity check
        self.check_symbol_sanity(metadata["pair"])

        # RSI
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Use named boolean variables
        # Long Entry: RSI < 30 and Volume > 0
        rsi_low = dataframe["rsi"] < 30
        has_volume = dataframe["volume"] > 0

        long_condition = rsi_low & has_volume

        dataframe.loc[long_condition, "enter_long"] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Long Exit: RSI > 70 and Volume > 0
        rsi_high = dataframe["rsi"] > 70
        has_volume = dataframe["volume"] > 0

        exit_condition = rsi_high & has_volume

        dataframe.loc[exit_condition, "exit_long"] = 1
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
        **kwargs: Any,
    ) -> bool:
        """
        Called right before placing a trade.
        """
        indicators = {}
        if self.dp:
            try:
                dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
                if not dataframe.empty:
                    last_candle = dataframe.iloc[-1]
                    indicators = {
                        "rsi": last_candle.get("rsi"),
                        "volume": last_candle.get("volume"),
                        "close": last_candle.get("close"),
                    }
            except Exception as e:
                indicators = {"error": str(e)}

        self.log_signal(
            pair=pair,
            side=side,
            reason=entry_tag or "Strategy Entry",
            ts_utc=current_time,
            indicators_snapshot=indicators,
        )
        return True

    def confirm_trade_exit(
        self,
        pair: str,
        trade: Trade,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        exit_reason: str,
        current_time: datetime,
        **kwargs: Any,
    ) -> bool:
        indicators = {}
        if self.dp:
            try:
                dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
                if not dataframe.empty:
                    last_candle = dataframe.iloc[-1]
                    indicators = {
                        "rsi": last_candle.get("rsi"),
                        "volume": last_candle.get("volume"),
                        "close": last_candle.get("close"),
                    }
            except Exception as e:
                indicators = {"error": str(e)}

        self.log_signal(
            pair=pair,
            side=trade.trade_direction,  # long or short
            reason=exit_reason,
            ts_utc=current_time,
            indicators_snapshot=indicators,
        )
        return True
