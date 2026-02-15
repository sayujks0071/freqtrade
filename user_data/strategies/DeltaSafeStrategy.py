"""
Strategy Name: DeltaSafeStrategy
Author: Unknown
Version: 1.0
Supported Timeframes: 1h

Supported Pair Format:
  - Delta contract symbols (e.g., BTCUSDT) vs Freqtrade/CCXT futures pair format (base/quote:settle like BTC/USDT:USDT)

Timezone Rule:
  - All timestamps logged as UTC ISO-8601

Entry Conditions:
  - Long: RSI < 30 and Volume > 0
  - Short: Disabled

Exit Conditions:
  - Long: RSI > 70 and Volume > 0
  - Short: Disabled

No Repainting:
  - Only act on closed candles (no incomplete candle usage)
"""

import sys
from datetime import datetime
from pathlib import Path

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.persistence import Trade
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
        self.symbol_sanity_check()

    def symbol_sanity_check(self):
        # Ensure config is available
        if not self.config:
            return

        whitelist = self.config.get("exchange", {}).get("pair_whitelist", [])
        for pair in whitelist:
            # Check for futures format: BASE/QUOTE:SETTLE
            # Simple check: must contain ':' and '/'
            if "/" not in pair or ":" not in pair:
                raise ValueError(
                    f"AUDIT_ERROR | Invalid pair format: {pair}. Expected BASE/QUOTE:SETTLE."
                )

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # RSI
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Check whitelist first (redundant if bot_start checked, but good for auditing per pair)
        self.assert_pair_in_whitelist(metadata["pair"])

        # Long entry logic
        # RSI < 30 and Volume > 0
        is_oversold = dataframe["rsi"] < 30
        has_volume = dataframe["volume"] > 0

        long_condition = is_oversold & has_volume
        dataframe.loc[long_condition, "enter_long"] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Long exit logic
        # RSI > 70 and Volume > 0
        is_overbought = dataframe["rsi"] > 70
        has_volume = dataframe["volume"] > 0

        long_exit_condition = is_overbought & has_volume
        dataframe.loc[long_exit_condition, "exit_long"] = 1

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
        # Get indicators snapshot
        # self.dp.get_analyzed_dataframe returns (dataframe, last_analyzed_time)
        # Note: self.dp might be None in backtesting/hyperopt, but this is strategy for live/dryrun.
        # In dry/live run, self.dp is available.

        indicators = {}
        if self.dp:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            if not dataframe.empty:
                last_row = dataframe.iloc[-1]
                indicators = {
                    "rsi": last_row.get("rsi"),
                    "volume": last_row.get("volume"),
                    "close": last_row.get("close"),
                }

        self.log_signal(
            pair=pair,
            side=side,
            reason=entry_tag or "Signal Confirmed",
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
        **kwargs,
    ) -> bool:
        """
        Called right before placing an exit trade.
        """
        # Get indicators snapshot
        indicators = {}
        if self.dp:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            if not dataframe.empty:
                last_row = dataframe.iloc[-1]
                indicators = {
                    "rsi": last_row.get("rsi"),
                    "volume": last_row.get("volume"),
                    "close": last_row.get("close"),
                }

        # Determine side (long/short) being exited
        side = "short" if getattr(trade, "is_short", False) else "long"

        self.log_signal(
            pair=pair,
            side=f"exit_{side}",
            reason=exit_reason,
            ts_utc=current_time,
            indicators_snapshot=indicators,
        )
        return True
