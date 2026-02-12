import logging
import os
from datetime import datetime, timezone

from freqtrade.persistence import Trade

logger = logging.getLogger(__name__)


class AuditedStrategyMixin:
    """
    Mixin for strategies to enforce safety checks and audit logging.
    Usage: class MyStrategy(IStrategy, AuditedStrategyMixin): ...
    """

    # Daily Loss Limit (Configurable via env or class var)
    # Default -5%
    daily_loss_limit = float(os.environ.get("DAILY_LOSS_LIMIT", -0.05))

    def log_signal(self, pair: str, signal: str, reason: str, metadata: dict = None):
        """
        Audit log for signals.
        """
        ts = datetime.now(timezone.utc).isoformat()
        msg = f"AUDIT_SIGNAL: timestamp={ts} pair={pair} signal={signal} reason={reason} metadata={metadata}"
        logger.info(msg)

    def check_daily_loss_limit(self, current_time: datetime) -> bool:
        """
        Check if we hit the daily loss limit.
        Returns True if trading is allowed, False if locked.
        """
        # Determine start of day (UTC)
        start_of_day = current_time.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)

        # We need to filter trades closed after start_of_day
        # Note: Trade.close_date is usually naive UTC in DB, so be careful with timezone comparison
        # Freqtrade DB usually stores naive UTC.

        trades = Trade.get_trades([Trade.close_date >= start_of_day.replace(tzinfo=None), Trade.is_open.is_(False)]).all()

        if not trades:
            return True

        daily_profit = sum(t.close_profit for t in trades)

        if daily_profit < self.daily_loss_limit:
            logger.warning(f"Daily Loss Limit Hit! Profit: {daily_profit:.4f} Limit: {self.daily_loss_limit:.4f}")
            return False

        return True

    def assert_pair_in_whitelist(self, pair: str) -> bool:
        """
        Enforce pair is in whitelist.
        """
        if hasattr(self, 'dp') and self.dp:
             if pair not in self.dp.current_whitelist():
                  logger.error(f"Pair {pair} is not in whitelist!")
                  return False
        return True
