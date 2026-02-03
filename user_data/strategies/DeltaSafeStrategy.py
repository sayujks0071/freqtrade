"""
Strategy name: DeltaSafeStrategy
Author: Unknown
Version: 1.0
Supported timeframes: 1h
Supported pair format: Base/Quote:Settle (e.g. BTC/USDT:USDT)
Timezone rule: UTC ISO-8601
Entry conditions: Check populate_entry_trend
Exit conditions: Check populate_exit_trend
No repainting: Validated
"""

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import IStrategy


# Add _base to path to allow import
sys.path.append(str(Path(__file__).parent / "_base"))
from AuditedStrategyMixin import AuditedStrategyMixin


logger = logging.getLogger(__name__)


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
        # Sanity Check: Ensure pair is in whitelist
        if not self.assert_pair_in_whitelist(metadata["pair"]):
            return dataframe

        # Logic: RSI < 30 and Volume > 0
        rsi_oversold = dataframe["rsi"] < 30
        has_volume = dataframe["volume"] > 0

        # Combine conditions
        long_cond = rsi_oversold & has_volume

        dataframe.loc[long_cond, "enter_long"] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Logic: RSI > 70 and Volume > 0
        rsi_overbought = dataframe["rsi"] > 70
        has_volume = dataframe["volume"] > 0

        # Combine conditions
        exit_long_cond = rsi_overbought & has_volume

        dataframe.loc[exit_long_cond, "exit_long"] = 1
        return dataframe

    def confirm_trade_entry(
        self,
        pair: str,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        current_time: datetime,
        entry_tag: str,
        side: str,
        **kwargs,
    ) -> bool:
        """
        Called right before placing a trade.
        """
        indicators = {}
        try:
            # Attempt to fetch analyzed dataframe to log indicators
            if self.dp:
                dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
                if dataframe is not None and not dataframe.empty:
                    last_candle = dataframe.iloc[-1]
                    indicators = {
                        "rsi": last_candle.get("rsi"),
                        "close": last_candle.get("close"),
                        "volume": last_candle.get("volume"),
                    }
        except Exception as e:
            logger.warning(f"Could not fetch indicators for audit log: {e}")

        self.log_signal(
            pair=pair,
            side=side,
            reason=f"Entry Signal Confirmed ({entry_tag})",
            ts_utc=current_time,
            indicators_snapshot=indicators,
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
        indicators = {}
        try:
            if self.dp:
                dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
                if dataframe is not None and not dataframe.empty:
                    last_candle = dataframe.iloc[-1]
                    indicators = {
                        "rsi": last_candle.get("rsi"),
                        "close": last_candle.get("close"),
                        "volume": last_candle.get("volume"),
                    }
        except Exception as e:
            logger.warning(f"Could not fetch indicators for audit log: {e}")

        # Determine side (safely)
        side = "unknown"
        if hasattr(trade, "is_short"):
            side = "short" if trade.is_short else "long"

        self.log_signal(
            pair=pair,
            side=side,
            reason=f"Exit Signal Confirmed ({exit_reason})",
            ts_utc=current_time,
            indicators_snapshot=indicators,
        )
        return True
