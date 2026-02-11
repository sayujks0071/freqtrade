"""
Strategy Name: DeltaSafeStrategy
Author: Freqtrade/Delta
Version: 1.1
Supported Timeframes: 1h

Supported Pair Format Notes:
    - Delta contract symbols (e.g. BTCUSDT)
    - Freqtrade/CCXT futures pair format (base/quote:settle like BTC/USDT:USDT)

Timezone Rule:
    - All timestamps logged as UTC ISO-8601

Entry Definitions:
    - Long entry: RSI < 30 and Volume > 0
    - Short entry: None

Exit Definitions:
    - Long exit: RSI > 70 and Volume > 0
    - Short exit: None

No Repainting Note:
    - Only act on closed candles (no incomplete candle usage)
"""

import sys
from contextlib import suppress
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

    def sanity_check_pair(self, pair: str) -> None:
        """
        Fail fast if pair format mismatches futures naming.
        """
        if ":" not in pair:
            raise ValueError(f"Pair {pair} does not match futures format (BASE/QUOTE:SETTLE)")

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # RSI
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        if not self.assert_pair_in_whitelist(metadata["pair"]):
            return dataframe

        self.sanity_check_pair(metadata["pair"])

        # RSI Check: Oversold condition
        is_oversold = dataframe["rsi"] < 30

        # Volume Check: Ensure liquidity
        has_volume = dataframe["volume"] > 0

        # Market Thesis: Enter long when oversold and liquid
        dataframe.loc[(is_oversold & has_volume), "enter_long"] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # RSI Check: Overbought condition
        is_overbought = dataframe["rsi"] > 70

        # Volume Check
        has_volume = dataframe["volume"] > 0

        # Market Thesis: Exit long when overbought and liquid
        dataframe.loc[(is_overbought & has_volume), "exit_long"] = 1

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
        # Fetch indicators snapshot
        indicators = {}
        try:
            # Try to get analyzed dataframe
            # Note: This might re-run analysis depending on freqtrade internals,
            # but usually it pulls from cache if within same iteration.
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            last_candle = dataframe.iloc[-1]
            indicators = {
                "rsi": last_candle.get("rsi"),
                "volume": last_candle.get("volume"),
                "close": last_candle.get("close"),
            }
        except Exception as e:
            # Fallback if DP not available or error
            indicators = {"error": str(e)}

        self.log_signal(
            pair=pair,
            side=side,
            reason="Signal Confirmed (RSI/Vol)",
            candle_date=current_time,
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
        # Fetch indicators snapshot
        indicators = {}
        with suppress(Exception):
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            last_candle = dataframe.iloc[-1]
            indicators = {
                "rsi": last_candle.get("rsi"),
                "volume": last_candle.get("volume"),
                "close": last_candle.get("close"),
            }

        self.log_signal(
            pair=pair,
            side="short" if trade.is_short else "long",
            reason=f"Exit Confirmed: {exit_reason}",
            candle_date=current_time,
            indicators_snapshot=indicators,
        )
        return True
