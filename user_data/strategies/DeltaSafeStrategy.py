"""
Strategy: DeltaSafeStrategy
Author: Google Jules
Version: 1.2
Timeframes: 1h
Pair format: Delta contract symbols (e.g. BTCUSDT) vs Freqtrade/CCXT futures pair format
             (base/quote:settle like BTC/USDT:USDT)
Timezone: UTC ISO-8601
Entry: Long entry conditions
Exit: Long exit conditions
No repainting: Only act on closed candles (no incomplete candle usage)
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

    def bot_start(self, **kwargs) -> None:
        """
        Called on startup. Validates pair whitelist format.
        """
        if self.config["exchange"].get("pair_whitelist"):
            for pair in self.config["exchange"]["pair_whitelist"]:
                # This will raise ValueError if format is invalid, stopping the bot.
                self.normalize_pair(pair)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # RSI
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        pair = metadata["pair"]

        # Ensure pair is in whitelist
        try:
            self.assert_pair_in_whitelist(pair, self.config["exchange"].get("pair_whitelist", []))
        except ValueError:
            return dataframe

        # Entry logic: RSI < 30 and Volume > 0 (using shift(1) for closed candle logic)
        rsi_low = dataframe["rsi"].shift(1) < 30
        volume_ok = dataframe["volume"].shift(1) > 0

        long_cond = rsi_low & volume_ok

        dataframe.loc[long_cond, "enter_long"] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Exit logic: RSI > 70 and Volume > 0 (using shift(1) for closed candle logic)
        rsi_high = dataframe["rsi"].shift(1) > 70
        volume_ok = dataframe["volume"].shift(1) > 0

        exit_cond = rsi_high & volume_ok

        dataframe.loc[exit_cond, "exit_long"] = 1
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
        # Get latest data
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        # Use -2 for last closed candle since process_only_new_candles=True
        last_candle = dataframe.iloc[-2].squeeze()

        snapshot = {
            "rsi": last_candle.get("rsi"),
            "close": last_candle.get("close"),
            "volume": last_candle.get("volume"),
        }

        self.log_signal(pair, side, "Signal Confirmed (Entry)", current_time, snapshot)
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
        """
        Called right before exiting a trade.
        """
        # Get latest data
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        # Use -2 for last closed candle
        last_candle = dataframe.iloc[-2].squeeze()

        snapshot = {
            "rsi": last_candle.get("rsi"),
            "close": last_candle.get("close"),
            "volume": last_candle.get("volume"),
        }

        self.log_signal(
            pair, "exit", f"Signal Confirmed (Exit: {exit_reason})", current_time, snapshot
        )
        return True
