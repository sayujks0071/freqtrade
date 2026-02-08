"""
Strategy: DeltaSafeStrategy
Author: Generated
Version: 1.1
Timeframe: 1h
Pair Format: Delta futures (e.g. BTCUSDT) or Freqtrade (e.g. BTC/USDT:USDT)
Timezone: UTC ISO-8601
Entry:
  - Long: RSI < 30 and Volume > 0
  - Short: Disabled
Exit:
  - Long: RSI > 70 and Volume > 0
  - Short: Disabled
Repainting: No (process_only_new_candles=True)
"""

import sys
from datetime import UTC, datetime
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

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # RSI
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Check whitelist first
        if self.config.get("exchange", {}).get("pair_whitelist"):
            if not self.assert_pair_in_whitelist(
                metadata["pair"], self.config["exchange"]["pair_whitelist"]
            ):
                return dataframe

        # Market Thesis: Buy when RSI is oversold (<30) and there is volume.
        # This indicates a potential reversal from a dip.

        long_rsi_condition = dataframe["rsi"] < 30
        long_volume_condition = dataframe["volume"] > 0

        dataframe.loc[
            (long_rsi_condition & long_volume_condition),
            "enter_long"
        ] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Market Thesis: Sell when RSI is overbought (>70) and there is volume.
        # This indicates a potential reversal from a peak.

        exit_long_rsi_condition = dataframe["rsi"] > 70
        exit_long_volume_condition = dataframe["volume"] > 0

        dataframe.loc[
            (exit_long_rsi_condition & exit_long_volume_condition),
            "exit_long"
        ] = 1
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
        # Snapshot indicators
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        # Use last closed candle (iloc[-2]) as per requirements for process_only_new_candles=True
        last_candle = dataframe.iloc[-2]

        snapshot = {
            "rsi": last_candle["rsi"],
            "volume": last_candle["volume"],
            "close": last_candle["close"],
            "date": str(last_candle["date"]),
        }

        self.log_signal(
            pair=pair,
            side=side,
            reason=entry_tag or "Signal Confirmed",
            ts_utc=current_time.astimezone(UTC),
            indicators_snapshot=snapshot,
        )
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

        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        last_candle = dataframe.iloc[-2]

        snapshot = {
            "rsi": last_candle["rsi"],
            "volume": last_candle["volume"],
            "close": last_candle["close"],
            "date": str(last_candle["date"]),
        }

        # Exit is opposite side? No, side usually refers to position side.
        # But log_signal expects 'side'. Usually side=buy/sell or long/short.
        # Here let's use the trade direction.
        # If trade is long, we are exiting long.
        self.log_signal(
            pair=pair,
            side="long" if trade.is_short else "short",
            reason=exit_reason,
            ts_utc=current_time.astimezone(UTC),
            indicators_snapshot=snapshot,
        )
        return True
