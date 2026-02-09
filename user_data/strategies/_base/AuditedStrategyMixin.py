# user_data/strategies/_base/AuditedStrategyMixin.py
import logging
from datetime import datetime, timezone
import pandas as pd
from freqtrade.persistence import Trade

logger = logging.getLogger(__name__)


class AuditedStrategyMixin:
    """
    Mixin for strategies to enforce audit logging and safety checks.
    """

    def log_signal(self, pair: str, side: str, reason: str, snapshot: dict = None):
        """
        Logs a trading signal with structured data.
        Format: AUDIT_SIGNAL | UTC_TIMESTAMP | PAIR | SIDE | REASON | SNAPSHOT
        """
        ts = datetime.now(timezone.utc).isoformat()
        snapshot_str = str(snapshot) if snapshot else "{}"
        logger.info(f"AUDIT_SIGNAL | {ts} | {pair} | {side} | {reason} | {snapshot_str}")

    def normalize_pair(self, pair: str) -> str:
        """
        Ensures pair format is correct (BASE/QUOTE:SETTLE).
        """
        if ":" not in pair:
            raise ValueError(f"Invalid pair format for futures: {pair}. Expected BASE/QUOTE:SETTLE")
        return pair.upper()

    def assert_pair_in_whitelist(self, pair: str):
        """
        Asserts that the pair is in the current whitelist.
        """
        if pair not in self.dp.current_whitelist():
            raise ValueError(f"Pair {pair} is not in the current whitelist!")

    def check_daily_loss_limit(self, max_daily_loss_pct: float) -> bool:
        """
        Checks if the daily realized loss exceeds the limit.
        Returns True if trading should STOP.
        """
        try:
            # Get today's trades
            today = datetime.now(timezone.utc).date()
            # This is simplified. In real prod, use DB query properly via self.dp or Trade model
            # Assuming we can access Trade model directly as we are in Freqtrade context

            # Use Trade.get_trades_proxy() or similar if available, but direct query is robust
            trades = Trade.get_trades_proxy(is_open=False, close_date=today)

            daily_profit = sum(t.close_profit_abs for t in trades if t.close_date.date() == today)

            # Calculate total stake (approximate or use current balance)
            # self.wallets.get_total_stake_amount() is available in strategy
            current_balance = self.wallets.get_total_stake_amount()

            if current_balance == 0:
                return False

            daily_profit_pct = daily_profit / current_balance

            if daily_profit_pct < -max_daily_loss_pct:
                logger.warning(f"Daily loss limit hit! PnL: {daily_profit_pct:.2%}, Limit: -{max_daily_loss_pct:.2%}")
                return True

            return False

        except Exception as e:
            logger.error(f"Error checking daily loss limit: {e}")
            return False  # Fail safe or fail open? Fail open to avoid locking out, but log error.
