"""
Strategy Name: DeltaSafeStrategy
Author: <Author>
Version: 1.0
Supported Timeframes: <Timeframes>
Supported Pair Format: Delta Futures (e.g. BTC/USDT:USDT)
Timezone: UTC (all timestamps in ISO-8601)

Entry Conditions:
  - Long: <Describe long entry conditions>
  - Short: <Describe short entry conditions>

Exit Conditions:
  - Long: <Describe long exit conditions>
  - Short: <Describe short exit conditions>

No Repainting: This strategy strictly acts on closed candles.
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

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # RSI
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Ensure pair is in whitelist
        self.assert_pair_in_whitelist(metadata["pair"])

        # RSI Oversold Condition
        is_oversold = dataframe["rsi"] < 30

        # Volume Condition
        has_volume = dataframe["volume"] > 0

        # Combine conditions
        long_condition = is_oversold & has_volume

        dataframe.loc[long_condition, "enter_long"] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # RSI Overbought Condition
        is_overbought = dataframe["rsi"] > 70

        # Volume Condition
        has_volume = dataframe["volume"] > 0

        # Combine conditions
        exit_condition = is_overbought & has_volume

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
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> bool:
        """
        Called right before placing a trade.
        """
        # Get indicators snapshot for audit
        # This requires backtesting or dry-run where dp is available
        indicators = {}
        if self.dp:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            if not dataframe.empty:
                last_candle = dataframe.iloc[-1].to_dict()
                indicators = {
                    "rsi": last_candle.get("rsi"),
                    "volume": last_candle.get("volume"),
                    "close": last_candle.get("close"),
                }

        self.log_signal(
            pair=pair,
            side=side,
            reason=entry_tag or "Signal Confirmed",
            ts_utc=current_time,
            indicators_snapshot=indicators
        )
        return True
