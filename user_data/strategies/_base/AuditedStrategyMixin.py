import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class AuditedStrategyMixin:
    """
    Mixin to enforce audit logging and standardized behaviors.
    """

    def log_signal(self, pair: str, signal: str, reason: str = "", current_time=None):
        """
        Logs a signal event in a structured way for audit purposes.
        """
        # noqa: UP017 - Use timezone.utc for compatibility with older python versions
        now = datetime.now(timezone.utc).isoformat()
        # Structured log format: UTC | PAIR | SIGNAL | REASON
        msg = f"AUDIT_LOG | {now} | {pair} | {signal} | {reason}"
        logger.info(msg)

    def assert_pair_in_whitelist(self, pair):
        if hasattr(self, "dp") and self.dp:
            if pair not in self.dp.current_whitelist():
                logger.warning(f"Strategy processing pair not in whitelist: {pair}")
