"""
Strategy: DeltaSafeStrategy
Author: Unknown
Version: 1.0
Timeframe: 1h
Pair Format: Delta Futures (e.g. BTC/USDT:USDT)
Timezone: UTC ISO-8601
Entry/Exit: Define me
Repainting: No repainting (process_only_new_candles=True)
"""

import sys
from pathlib import Path

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import IStrategy

# Add _base to path to allow import
sys.path.append(str(Path(__file__).parent / "_base"))

from AuditedStrategyMixin import AuditedStrategyMixin  # noqa: E402


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
        Called on startup. Validate whitelist.
        """
        if self.config.get("exchange", {}).get("pair_whitelist"):
            for pair in self.config["exchange"]["pair_whitelist"]:
                self.normalize_pair(pair)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # RSI
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Check whitelist before processing
        if self.config.get("exchange", {}).get("pair_whitelist"):
            self.assert_pair_in_whitelist(
                metadata["pair"], self.config["exchange"]["pair_whitelist"]
            )

        # RSI Over-sold condition
        long_rsi = dataframe["rsi"] < 30

        # Volume filter
        volume_check = dataframe["volume"] > 0

        # Combined Entry Condition
        # Market Thesis: Enter long when RSI is oversold (<30) and there is volume activity.
        enter_long = long_rsi & volume_check

        dataframe.loc[enter_long, "enter_long"] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # RSI Over-bought condition
        long_rsi_exit = dataframe["rsi"] > 70

        # Volume filter
        volume_check = dataframe["volume"] > 0

        # Combined Exit Condition
        # Market Thesis: Exit long when RSI is overbought (>70) and liquidity exists.
        exit_long = long_rsi_exit & volume_check

        dataframe.loc[exit_long, "exit_long"] = 1
        return dataframe

    def confirm_trade_entry(
        self,
        pair: str,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        current_time,
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

        snapshot = {
            "rsi": last_candle.get("rsi"),
            "volume": last_candle.get("volume"),
            "close": last_candle.get("close"),
        }

        self.log_signal(
            pair=pair,
            side=side,
            reason=f"Entry Signal {entry_tag}",
            ts_utc=current_time,
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
        sell_reason: str,
        current_time,
        **kwargs,
    ) -> bool:
        # Snapshot indicators
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        last_candle = dataframe.iloc[-1].squeeze()

        snapshot = {
            "rsi": last_candle.get("rsi"),
            "volume": last_candle.get("volume"),
            "close": last_candle.get("close"),
        }

        self.log_signal(
            pair=pair,
            side=trade.trade_direction,
            reason=f"Exit Signal {sell_reason}",
            ts_utc=current_time,
            indicators_snapshot=snapshot,
        )
        return True
