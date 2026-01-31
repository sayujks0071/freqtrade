"""
AuditedStrategyMixin
Mixin class for strategies to enforce audit logging and safety checks.
"""
import logging
from datetime import datetime, timezone
from freqtrade.strategy import IStrategy
from pandas import DataFrame

logger = logging.getLogger(__name__)

class AuditedStrategyMixin:
    """
    Mixin for strategies to enforce audit logging and safety checks.
    """

    def log_signal(self, pair: str, timeframe: str, direction: str, reason: str, candle_date: datetime):
        """
        Log entry/exit signals to audit log.
        """
        # This logs to standard freqtrade log, but could be directed to a separate file or DB.
        # Freqtrade logs are captured.
        # Format: AUDIT_SIGNAL | TIMESTAMP | PAIR | DIRECTION | REASON | CANDLE
        msg = f"AUDIT_SIGNAL | {datetime.now(timezone.utc).isoformat()} | {pair} | {direction} | {reason} | {candle_date}"
        logger.info(msg)

    def check_whitelist(self, pair: str):
        """
        Assert pair is in current whitelist.
        """
        if self.config['exchange'].get('pair_whitelist'):
            if pair not in self.config['exchange']['pair_whitelist']:
                logger.warning(f"AUDIT_WARNING | Pair {pair} not in whitelist but processing!")
                return False
        return True

    # Override IStrategy methods to inject logging if possible,
    # but Mixins usually require explicit calls or MRO tricks.
    # To keep it simple, we provide helper methods that the strategy SHOULD call.

    # Alternatively, we can use a wrapper if we inherit from IStrategy here?
    # No, Mixin is better.
