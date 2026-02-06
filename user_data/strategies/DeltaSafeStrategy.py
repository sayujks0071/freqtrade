"""
Strategy Name: DeltaSafeStrategy
    Author: Unknown
    Version: 1.0
    Supported Timeframes: Unknown

    Supported Pair Format:
      - Delta Contract: BTCUSDT (Example)
      - Freqtrade/CCXT: BTC/USDT:USDT (Example)

    Timezone:
      - All timestamps logged as UTC ISO-8601

    Entry Conditions:
      - Long: TODO: Describe long entry
      - Short: TODO: Describe short entry (or N/A)

    Exit Conditions:
      - Long: TODO: Describe long exit
      - Short: TODO: Describe short exit (or N/A)

    No Repainting:
      - This strategy strictly acts on closed candles.
      - No logic is based on incomplete/current candle data.
"""

import sys
from pathlib import Path
from datetime import datetime

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

    def validate_pair_format(self, pair: str) -> None:
        """
        Sanity check for pair format.
        Must match BASE/QUOTE:SETTLE for Delta Futures.
        """
        if ":" not in pair or "/" not in pair:
            raise ValueError(f"Pair {pair} does not match Futures format BASE/QUOTE:SETTLE")

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # RSI
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        pair = metadata["pair"]
        self.validate_pair_format(pair)

        # Market Thesis:
        # Enter Long if RSI is oversold (< 30) indicating a potential reversal,
        # and there is volume to support the move.

        rsi_oversold = (dataframe["rsi"] < 30)
        has_volume = (dataframe["volume"] > 0)

        long_entry = (rsi_oversold & has_volume)

        dataframe.loc[long_entry, "enter_long"] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Market Thesis:
        # Exit Long if RSI is overbought (> 70) indicating potential pullback,
        # and there is volume.

        rsi_overbought = (dataframe["rsi"] > 70)
        has_volume = (dataframe["volume"] > 0)

        long_exit = (rsi_overbought & has_volume)

        dataframe.loc[long_exit, "exit_long"] = 1
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
        # Capture snapshot of the LAST CLOSED candle (-2) which triggered the signal.
        # -1 is the current open candle.
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if not dataframe.empty and len(dataframe) >= 2:
            closed_candle = dataframe.iloc[-2]
            snapshot = {
                "rsi": closed_candle.get("rsi"),
                "close": closed_candle.get("close"),
                "volume": closed_candle.get("volume")
            }
        else:
            snapshot = {"error": "no_data"}

        self.log_signal(pair, side, "Signal Confirmed", current_time, snapshot)
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
        Called right before placing an exit order.
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if not dataframe.empty and len(dataframe) >= 2:
            closed_candle = dataframe.iloc[-2]
            snapshot = {
                "rsi": closed_candle.get("rsi"),
                "close": closed_candle.get("close"),
                "volume": closed_candle.get("volume")
            }
        else:
            snapshot = {"error": "no_data"}

        # trade object available, check side
        side = "short" if getattr(trade, "is_short", False) else "long"

        self.log_signal(pair, side, f"Exit: {exit_reason}", current_time, snapshot)
        return True
