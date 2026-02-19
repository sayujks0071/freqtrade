"""
Strategy Name: DeltaSafeStrategy
Author: Freqtrade User
Version: 1.1
Timeframes: 1h
Supported Pair Format: Delta contract symbols (e.g., BTCUSDT) vs Freqtrade/CCXT
futures pair format (base/quote:settle like BTC/USDT:USDT)
Timezone Rule: all timestamps logged as UTC ISO-8601
Entry/Exit Definitions:
  - Long entry conditions: RSI < 30 and Volume > 0
  - Long exit conditions: RSI > 70 and Volume > 0
  - Short entry conditions: None
  - Short exit conditions: None
No Repainting: only act on closed candles (no incomplete candle usage)
"""

import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import IStrategy


logger = logging.getLogger(__name__)

# Add _base to path to allow import
sys.path.append(str(Path(__file__).parent / "_base"))
from AuditedStrategyMixin import AuditedStrategyMixin  # noqa: E402, RUF100


class DeltaSafeStrategy(AuditedStrategyMixin, IStrategy):
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

    def check_symbol_format(self, pair: str) -> None:
        """
        Fail fast if pair format mismatches futures naming.
        Delta Futures format: BASE/QUOTE:SETTLE (e.g. BTC/USDT:USDT)
        """
        if ":" not in pair:
            # Just a warning or strict fail?
            # Prompt says: "Any symbol mismatch causes a clear startup failure before trading begins."
            # But populate_entry_trend is called per pair.
            # We can raise an error here.
            raise ValueError(
                f"AUDIT_FAIL: Pair '{pair}' does not look like a futures pair (missing :settle)."
            )

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        pair = metadata["pair"]
        self.check_symbol_format(pair)

        # Check whitelist using mixin
        # Note: self.config is available in IStrategy
        if self.config.get("exchange", {}).get("pair_whitelist"):
            try:
                self.assert_pair_in_whitelist(
                    pair, self.config["exchange"]["pair_whitelist"]
                )
            except ValueError as e:
                # Log error and return empty? Or let it crash?
                # If we crash, it stops the bot. That is what "fail fast" implies.
                raise e

        # Named boolean conditions
        # RSI < 30 indicates oversold conditions
        is_oversold = dataframe["rsi"] < 30
        # Volume > 0 ensures there is liquidity
        has_volume = dataframe["volume"] > 0

        # Combine
        dataframe.loc[(is_oversold & has_volume), "enter_long"] = 1

        # Log reason tag
        dataframe.loc[
            (is_oversold & has_volume), "enter_tag"
        ] = "rsi_oversold_volume"

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Named boolean conditions
        # RSI > 70 indicates overbought conditions
        is_overbought = dataframe["rsi"] > 70
        has_volume = dataframe["volume"] > 0

        dataframe.loc[(is_overbought & has_volume), "exit_long"] = 1

        dataframe.loc[
            (is_overbought & has_volume), "exit_tag"
        ] = "rsi_overbought_volume"

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
        # Snapshot indicators (dummy here, but in real use we would get them from dataframe)
        # We can't easily get the *exact* dataframe row here efficiently without lookup.
        # But we can log what we know.

        # For simplicity, we just log "check logs for indicators" or pass empty dict
        # if not easily available.
        # However, we can try to get the last analyzed candle if we had the dataframe.
        # IStrategy doesn't pass dataframe to confirm_trade_entry.
        # But self.dp.get_analyzed_dataframe(pair, timeframe) is available if dataprovider is set.

        indicators = {}
        if self.dp:
            try:
                dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
                last_candle = dataframe.iloc[-1]
                indicators = {
                    "rsi": last_candle.get("rsi"),
                    "volume": last_candle.get("volume"),
                    "close": last_candle.get("close"),
                }
            except Exception:  # noqa: S110
                # Fallback if dataframe retrieval fails
                pass

        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=UTC)

        self.log_signal(
            pair=pair,
            side=side,
            reason=f"Signal Confirmed (Tag: {entry_tag})",
            ts_utc=current_time,  # confirm_trade_entry passes datetime object
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
        if self.dp:
            try:
                dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
                last_candle = dataframe.iloc[-1]
                indicators = {
                    "rsi": last_candle.get("rsi"),
                    "volume": last_candle.get("volume"),
                    "close": last_candle.get("close"),
                }
            except Exception:  # noqa: S110
                # Fallback if dataframe retrieval fails
                pass

        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=UTC)

        # Determine side based on trade object
        # Assuming trade object has is_short (Freqtrade standard)
        side = "short" if getattr(trade, "is_short", False) else "long"

        self.log_signal(
            pair=pair,
            side=side,
            reason=f"Exit Confirmed (Reason: {exit_reason})",
            ts_utc=current_time,
            indicators_snapshot=indicators,
        )
        return True
