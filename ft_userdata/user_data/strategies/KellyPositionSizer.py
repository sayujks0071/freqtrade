"""
Kelly Criterion Portfolio Manager
==================================

System Hypothesis:
    Position sizing is more important than entry/exit signals.
    The Kelly Criterion calculates the optimal bet size to maximize
    geometric growth while avoiding ruin.

Formula:
    K = W - ((1 - W) / R)
    Where:
    K = Kelly fraction
    W = Win probability
    R = Win/Loss ratio

Implementation:
    - Calculates dynamic position size based on recent strategy performance
    - Applies "Half Kelly" for safety (fractional Kelly)
    - Enforces hard risk limits per trade

Usage:
    Import this module in your strategy to override `custom_stake_amount`.

Author: Elite Trading Strategist
Version: 1.0.0
"""

import logging
from pandas import DataFrame
import numpy as np

logger = logging.getLogger(__name__)


class KellyPositionSizer:
    def __init__(self, config: dict):
        self.config = config
        self.max_stake_ratio = 0.20  # Never risk more than 20% on one trade
        self.kelly_fraction = 0.5  # Half Kelly for safety

        # Default stats if no history
        self.default_win_rate = 0.55
        self.default_risk_reward = 1.5

    def get_stake_amount(
        self,
        pair: str,
        current_balance: float,
        current_price: float,
        history: DataFrame = None,
    ) -> float:
        """
        Calculate optimal position size using Kelly Criterion
        """

        # 1. Get Performance Stats
        if history is not None and len(history) > 20:
            win_rate = len(history[history["profit_abs"] > 0]) / len(history)

            avg_win = history[history["profit_abs"] > 0]["profit_abs"].mean()
            avg_loss = abs(history[history["profit_abs"] < 0]["profit_abs"].mean())

            if avg_loss > 0:
                risk_reward_ratio = avg_win / avg_loss
            else:
                risk_reward_ratio = self.default_risk_reward
        else:
            # Use defaults if not enough history
            win_rate = self.default_win_rate
            risk_reward_ratio = self.default_risk_reward

        # 2. Calculate Kelly Percentage
        # K = W - ((1 - W) / R)
        if risk_reward_ratio == 0:
            kelly_pct = 0
        else:
            kelly_pct = win_rate - ((1 - win_rate) / risk_reward_ratio)

        # 3. Apply Fractional Kelly (Safety)
        safe_kelly = kelly_pct * self.kelly_fraction

        # 4. Clip to Limits (0% to Max Cap)
        position_size_pct = np.clip(safe_kelly, 0.01, self.max_stake_ratio)

        # 5. Calculate Absolute Stake
        stake_amount = current_balance * position_size_pct

        logger.info(
            f"Kelly Calc for {pair}: WinRate={win_rate:.2f}, R={risk_reward_ratio:.2f} -> "
            f"Kelly={kelly_pct:.2f} -> Safe={position_size_pct:.2f} -> Amount={stake_amount:.2f}"
        )

        return stake_amount


# Example Strategy Integration:
#
# def custom_stake_amount(self, pair: str, current_time: datetime, current_rate: float,
#                        current_balance: float, **kwargs) -> float:
#
#     return self.kelly.get_stake_amount(pair, current_balance, current_rate, self.history)
