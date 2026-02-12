"""
Strategy Name: DeltaSafeStrategy
Author: Frequency Trade User
Version: 1.1
Timeframes: 1h
Pair Format: Delta symbols (e.g. BTCUSDT) vs Freqtrade (BTC/USDT:USDT)
Timezone: UTC ISO-8601
Entry Conditions:
  - Long: RSI < 30 and Volume > 0
  - Short: None
Exit Conditions:
  - Long: RSI > 70 and Volume > 0
  - Short: None
No Repainting: Logic runs on closed candles only.
"""

import sys
from datetime import datetime
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
        pair = metadata["pair"]
        if self.config.get("exchange", {}).get("pair_whitelist"):
            if not self.assert_pair_in_whitelist(pair, self.config["exchange"]["pair_whitelist"]):
                return dataframe

        # Named boolean conditions
        # RSI oversold condition
        is_oversold = dataframe["rsi"] < 30

        # Volume check to ensure liquidity
        has_volume = dataframe["volume"] > 0

        # Combine conditions
        long_condition = is_oversold & has_volume

        dataframe.loc[long_condition, "enter_long"] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # RSI overbought condition
        is_overbought = dataframe["rsi"] > 70

        # Volume check
        has_volume = dataframe["volume"] > 0

        # Combine conditions
        exit_long_condition = is_overbought & has_volume

        dataframe.loc[exit_long_condition, "exit_long"] = 1
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
        last_candle = dataframe.iloc[-1].squeeze()

        indicators_snapshot = {
            "rsi": last_candle.get("rsi"),
            "volume": last_candle.get("volume"),
            "close": last_candle.get("close")
        }

        reason = "RSI < 30 and Volume > 0" if side == "long" else "Unknown"

        self.log_signal(
            pair=pair,
            side=side,
            reason=reason,
            ts_utc=current_time,
            indicators_snapshot=indicators_snapshot
        )
        return True
