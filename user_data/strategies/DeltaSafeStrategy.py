"""
Strategy Name: DeltaSafeStrategy
Author: Jules
Version: 1.1
Supported Timeframes: 1h

Supported Pair Format Notes:
- Delta contract symbols (e.g., BTCUSDT) must be mapped to Freqtrade/CCXT futures pair format (base/quote:settle like BTC/USDT:USDT).

Timezone Rule:
- All timestamps logged as UTC ISO-8601.

Entry/Exit Definitions:
- Long Entry: RSI < 30 and Volume > 0
- Long Exit: RSI > 70 and Volume > 0
- Short Entry: N/A
- Short Exit: N/A

No Repainting Note:
- Only act on closed candles (no incomplete candle usage).
"""

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import IStrategy


# Add _base to path to allow import
sys.path.append(str(Path(__file__).parent / "_base"))
from AuditedStrategyMixin import AuditedStrategyMixin  # noqa: E402, RUF100

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

    def bot_start(self, **kwargs) -> None:
        """
        Called only once after bot instantiation.
        """
        # Symbol Sanity Check
        # Check if pairs in whitelist are formatted correctly for Delta Futures
        if self.config.get("exchange", {}).get("pair_whitelist"):
             for pair in self.config["exchange"]["pair_whitelist"]:
                 # Check for colon in pair (e.g. BTC/USDT:USDT)
                 if ":" not in pair:
                     error_msg = f"Symbol sanity failure: {pair} missing settle currency (e.g. :USDT). Required for Delta Futures."
                     logger.error(error_msg)
                     raise ValueError(error_msg)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # RSI
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Check whitelist first
        whitelist = self.config.get("exchange", {}).get("pair_whitelist", [])
        try:
            self.assert_pair_in_whitelist(metadata["pair"], whitelist)
        except ValueError:
            return dataframe

        # Named boolean conditions
        # RSI oversold condition
        rsi_oversold = (dataframe["rsi"] < 30)
        # Volume filter
        volume_ok = (dataframe["volume"] > 0)

        # Long entry
        long_entry = rsi_oversold & volume_ok

        dataframe.loc[long_entry, "enter_long"] = 1

        # Comments explaining market thesis
        # We enter long when RSI is oversold (<30) indicating potential reversal,
        # and there is volume activity to support the move.

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Named boolean conditions
        # RSI overbought condition
        rsi_overbought = (dataframe["rsi"] > 70)
        # Volume filter
        volume_ok = (dataframe["volume"] > 0)

        # Long exit
        long_exit = rsi_overbought & volume_ok

        dataframe.loc[long_exit, "exit_long"] = 1

        # Comments explaining market thesis
        # We exit long when RSI is overbought (>70) indicating overextension.

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
        # Capture indicators snapshot if possible
        # We need the last closed candle indicators
        snapshot = {}
        try:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            last_candle = dataframe.iloc[-1]
            snapshot = {
                "rsi": last_candle.get("rsi"),
                "close": last_candle.get("close"),
                "volume": last_candle.get("volume")
            }
        except Exception as e:
            logger.warning(f"Could not fetch snapshot for {pair}: {e}")

        self.log_signal(
            pair=pair,
            side=side,
            reason=entry_tag or "Signal Confirmed",
            ts_utc=current_time.replace(tzinfo=timezone.utc) if current_time.tzinfo is None else current_time,
            indicators_snapshot=snapshot
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
        current_time,
        **kwargs,
    ) -> bool:

        snapshot = {}
        try:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            last_candle = dataframe.iloc[-1]
            snapshot = {
                "rsi": last_candle.get("rsi"),
                "close": last_candle.get("close"),
                "volume": last_candle.get("volume")
            }
        except Exception as e:
            logger.warning(f"Could not fetch snapshot for {pair}: {e}")

        self.log_signal(
            pair=pair,
            side=trade.trade_direction,
            reason=exit_reason,
            ts_utc=current_time.replace(tzinfo=timezone.utc) if current_time.tzinfo is None else current_time,
            indicators_snapshot=snapshot
        )
        return True
