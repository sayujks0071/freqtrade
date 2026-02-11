"""
AuditedStrategyMixin
Mixin class for strategies to enforce audit logging and safety checks.
"""

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from freqtrade.persistence import Trade

if TYPE_CHECKING:
    from freqtrade.wallets import Wallets


logger = logging.getLogger(__name__)


class AuditedStrategyMixin:
    """
    Mixin for strategies to enforce audit logging and safety checks.
    """

    # Type hint for the config attribute expected from IStrategy
    config: dict[str, Any]
    if TYPE_CHECKING:
        wallets: "Wallets"

    def log_signal(
        self,
        pair: str,
        timeframe: str,
        direction: str,
        reason: str,
        candle_date: datetime,
    ) -> None:
        """
        Log entry/exit signals to audit log.
        """
        # Format: AUDIT_SIGNAL | TIMESTAMP | PAIR | DIRECTION | REASON | CANDLE
        msg = (
            f"AUDIT_SIGNAL | {datetime.now(UTC).isoformat()} | {pair} | "
            f"{direction} | {reason} | {candle_date}"
        )
        logger.info(msg)

    def check_whitelist(self, pair: str) -> bool:
        """
        Assert pair is in current whitelist.
        """
        if self.config.get("exchange", {}).get("pair_whitelist"):
            if pair not in self.config["exchange"]["pair_whitelist"]:
                logger.warning(
                    f"AUDIT_WARNING | Pair {pair} not in whitelist but processing!"
                )
                return False
        return True

    def normalize_pair(self, pair: str) -> str:
        """
        Normalize pair to uppercase.
        """
        return pair.upper()

    def check_daily_loss_limit(self, max_loss_ratio: float) -> bool:
        """
        Check if realized daily loss exceeds limit.
        Returns True if trading is allowed (loss < limit), False otherwise.
        """
        try:
            # Calculate today's start
            today_start = datetime.now(UTC).replace(
                hour=0, minute=0, second=0, microsecond=0
            )

            # Query closed trades for today using proxy (works for DB and Backtest)
            trades = Trade.get_trades_proxy(is_open=False, close_date=today_start)

            if not trades:
                return True

            total_profit_abs = sum(t.close_profit_abs for t in trades if t.close_profit_abs)

            # Assuming self.wallets is available in strategy
            # Use total_investment or available_capital if wallets not available?
            # self.wallets might be available.
            # If not, we can't calculate ratio accurately.
            # Fallback to config 'stake_amount' * 'max_open_trades' as rough capital estimate
            # if wallets fail?

            try:
                # Use getattr to avoid mypy error if wallets is not typed on Mixin explicitly
                wallets = getattr(self, "wallets", None)
                if wallets:
                    current_balance = wallets.get_total(self.config["stake_currency"])
                else:
                    current_balance = 0.0
            except Exception:
                # Fallback if wallets not initialized (e.g. some tests)
                current_balance = 0.0

            if current_balance == 0.0:
                # Try to estimate from config
                stake = self.config.get("stake_amount", 20)
                if isinstance(stake, str) and stake == "unlimited":
                    stake = 1000  # Dummy
                max_trades = self.config.get("max_open_trades", 5)
                current_balance = float(stake) * max_trades

            # Starting balance ~ current - profit
            starting_balance = current_balance - total_profit_abs

            if starting_balance <= 0:
                starting_balance = 1.0  # Avoid div by zero

            loss_ratio = total_profit_abs / starting_balance

            # If total_profit_abs is negative (loss), loss_ratio is negative.
            # e.g. -100 profit on 1000 balance => -0.1 ratio.
            # max_loss_ratio is positive (e.g. 0.05 for 5%)

            if loss_ratio < -max_loss_ratio:
                logger.warning(
                    f"AUDIT_RISK | Daily loss limit hit! "
                    f"Loss: {loss_ratio:.2%}, Limit: {max_loss_ratio:.2%}"
                )
                return False

            return True

        except Exception as e:
            logger.error(f"AUDIT_ERROR | Failed to check daily loss: {e}")
            return True  # Fail open
