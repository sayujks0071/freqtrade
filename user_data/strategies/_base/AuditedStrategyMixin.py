"""
Audited Strategy Mixin
"""
import logging
from datetime import datetime, timezone
from freqtrade.strategy import IStrategy

logger = logging.getLogger(__name__)

class AuditedStrategyMixin(IStrategy):
    """
    Mixin to enforce audit logging and safety checks.
    Must be inherited by all strategies.
    """

    def log_signal(self, pair: str, side: str, reason: str, indicators: dict = None):
        """
        Logs a structured audit signal.
        """
        ts = datetime.now(timezone.utc).isoformat()
        ind_str = str(indicators) if indicators else "{}"
        # Format: AUDIT_SIGNAL | UTC | PAIR | SIDE | REASON | INDICATORS
        log_msg = f"AUDIT_SIGNAL | {ts} | {pair} | {side} | {reason} | {ind_str}"
        logger.info(log_msg)

    def assert_pair_in_whitelist(self, pair: str):
        """
        Verifies that the pair is in the active whitelist.
        """
        if self.config['exchange'].get('pair_whitelist'):
            if pair not in self.config['exchange']['pair_whitelist']:
                logger.warning(f"AUDIT_FAIL: Pair {pair} not in whitelist!")
                # In backtesting this might be fine if whitelist is dynamic,
                # but in live this is a safety check.
                # We don't raise error to avoid crashing bot, but we log warning.
                return False
        return True

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float,
                            time_in_force: str, current_time: datetime, entry_tag: str | None,
                            side: str, **kwargs) -> bool:

        # Check whitelist
        if not self.assert_pair_in_whitelist(pair):
            return False

        # Log Audit
        self.log_signal(pair, side, entry_tag or "unknown", {})

        return True
