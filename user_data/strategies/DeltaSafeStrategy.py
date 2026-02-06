"""
    # Strategy: DeltaSafeStrategy
    # Author: Jules
    # Version: 1.0
    # Timeframe: 5m
    # Pair Format: BASE/QUOTE:SETTLE
    # Timezone: UTC
    # Entry/Exit: Limit/Limit
    # Repainting: No
"""
import logging
from datetime import datetime, timezone
from pandas import DataFrame
from typing import Dict, List, Any
from freqtrade.strategy import IStrategy, IntParameter

# Import mixin.
# Freqtrade adds user_data/strategies to path.
try:
    from _base.AuditedStrategyMixin import AuditedStrategyMixin
except ImportError:
    # Fallback if _base is not directly importable (e.g. running outside freqtrade context)
    # We define a dummy mixin to allow import without crashing
    class AuditedStrategyMixin:
        def log_signal(self, pair, side, reason, snapshot=None):
            pass
        def assert_pair_in_whitelist(self, pair):
            return True

logger = logging.getLogger(__name__)

class DeltaSafeStrategy(IStrategy, AuditedStrategyMixin):

    # ROI table:
    minimal_roi = {
        "60": 0.01,
        "30": 0.02,
        "0": 0.04
    }

    stoploss = -0.10
    timeframe = '5m'

    # Trailing stop:
    trailing_stop = False

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Simple sample logic: Always enter long if volume > 0 (for testing)
        dataframe.loc[
            (
                (dataframe['volume'] > 0)
            ),
            'enter_long'] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe['volume'] > 0)
            ),
            'exit_long'] = 0
        return dataframe

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float,
                            time_in_force: str, current_time: datetime, entry_tag: str,
                            side: str, **kwargs) -> bool:

        # 1. Audit Log
        self.log_signal(pair, side, "ENTRY_SIGNAL", {"rate": rate, "amount": amount})

        # 2. Safety Check
        if not self.assert_pair_in_whitelist(pair):
            return False

        return True

    def confirm_trade_exit(self, pair: str, trade: Any, order_type: str, amount: float,
                           rate: float, time_in_force: str, exit_reason: str,
                           current_time: datetime, **kwargs) -> bool:

        profit = trade.calc_profit_ratio(rate)
        self.log_signal(pair, "exit", exit_reason, {"profit": profit})
        return True
