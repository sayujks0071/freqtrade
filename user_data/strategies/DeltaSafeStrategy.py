"""
Strategy Name: DeltaSafeStrategy
Author: Unknown
Version: 1.0
Supported timeframes: 1h, 4h
Supported pair format: Delta Futures (e.g. BTCUSDT) normalized to BASE/QUOTE:SETTLE
Timezone: UTC ISO-8601
Entry definitions:
  - Long entry: RSI < 30
Exit definitions:
  - Long exit: RSI > 70
No repainting: Logic runs on closed candles only.
"""

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

    def symbol_sanity_check(self, pair: str) -> None:
        """
        Verify that the pair format matches Delta Futures requirements.
        Expected format: BASE/QUOTE:SETTLE (e.g. BTC/USDT:USDT)
        """
        if ":" not in pair:
             raise ValueError(f"Invalid Pair Format: {pair} (Missing settle currency)")
        if "/" not in pair:
             raise ValueError(f"Invalid Pair Format: {pair} (Missing quote currency separator)")

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # RSI
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        pair = metadata["pair"]
        self.symbol_sanity_check(pair)

        # Whitelist check from mixin
        # assert_pair_in_whitelist raises ValueError if not in whitelist
        # We catch it to avoid crashing the strategy loop, just return empty signal
        try:
            self.assert_pair_in_whitelist(pair)
        except ValueError:
            return dataframe

        # Named boolean conditions
        is_rsi_low = (dataframe["rsi"] < 30)
        is_volume_valid = (dataframe["volume"] > 0)

        entry_condition = (is_rsi_low & is_volume_valid)

        dataframe.loc[entry_condition, "enter_long"] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Named boolean conditions
        is_rsi_high = (dataframe["rsi"] > 70)
        is_volume_valid = (dataframe["volume"] > 0)

        exit_condition = (is_rsi_high & is_volume_valid)

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
        entry_tag,
        side: str,
        **kwargs,
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
                    indicators["rsi"] = last_candle.get("rsi")
                    indicators["volume"] = last_candle.get("volume")
                    indicators["close"] = last_candle.get("close")
            except Exception:
                pass

        reason = f"Signal Confirmed ({entry_tag})"

        self.log_signal(
            pair=pair,
            side=side,
            reason=reason,
            ts_utc=current_time,
            indicators_snapshot=indicators,
        )
        return True
