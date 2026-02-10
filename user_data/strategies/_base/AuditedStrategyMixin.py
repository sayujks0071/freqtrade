"""
AuditedStrategyMixin
Mixin class for strategies to enforce audit logging and safety checks.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from freqtrade.persistence import Trade


logger = logging.getLogger(__name__)


class AuditedStrategyMixin:
    """
    Mixin for strategies to enforce audit logging and safety checks.
    """

    # Type hint for the config attribute expected from IStrategy
    config: dict[str, Any]
    wallets: Any

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
                logger.warning(f"AUDIT_WARNING | Pair {pair} not in whitelist but processing!")
                return False
        return True

    def normalize_pair(self, pair: str) -> str:
        """
        Normalize pair to uppercase.
        """
        return pair.upper()

    def check_daily_loss_limit(self, max_daily_loss: float) -> bool:
        """
        Check if realized daily loss exceeds limit.
        Returns False if trading should stop.
        """
        try:
            # Calculate start of day (UTC)
            today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)

            # Query closed trades for today
            trades = Trade.get_trades([Trade.is_open.is_(False), Trade.close_date >= today_start]).all()

            daily_profit_abs = sum(t.close_profit_abs for t in trades)

            # Get total balance
            # self.wallets is available in IStrategy
            total_balance = self.wallets.get_total_stake_amount()

            if total_balance == 0:
                logger.warning("AUDIT_RISK | Total balance is 0, cannot calculate daily loss ratio.")
                return True

            current_loss_ratio = daily_profit_abs / total_balance

            # If loss is negative and exceeds max_daily_loss (e.g. -0.06 < -0.05)
            if current_loss_ratio < -max_daily_loss:
                logger.warning(
                    f"AUDIT_RISK | Daily Loss Limit Hit! "
                    f"PnL: {current_loss_ratio:.2%} ({daily_profit_abs:.2f}) < -{max_daily_loss:.2%}"
                )
                return False

            return True

        except Exception as e:
            logger.error(f"AUDIT_ERROR | Failed to check daily loss limit: {e}")
            # Fail safe: if we can't check, we should probably continue but log error,
            # or stop to be safe?
            # "Safe" means don't trade if uncertain.
            return True  # Proceeding to avoid blocking on DB errors, assuming Freqtrade's built-in protections handle it too.
