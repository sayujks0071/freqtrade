import json
import logging
from datetime import UTC, datetime
from typing import Any


# Set up a logger
logger = logging.getLogger(__name__)


class AuditedStrategyMixin:
    """
    Mixin to provide audit logging and safety checks for strategies.
    Strategies using this must also inherit from IStrategy.
    """

    def log_signal(
        self, pair: str, side: str, reason: str, snapshot: dict[str, Any] | None = None
    ) -> None:
        """
        Logs a structured audit message for a signal.
        """
        # Ensure UTC
        timestamp = datetime.now(UTC).isoformat()

        # Structure the log
        # We use a JSON object serialized to string so it can be parsed later
        audit_record = {
            "type": "AUDIT_SIGNAL",
            "timestamp": timestamp,
            "pair": pair,
            "side": side,
            "reason": reason,
            "snapshot": snapshot or {}
        }

        # Log as INFO
        # We use a specific prefix to easily grep or parse later
        # Freqtrade logs format is usually "timestamp - name - level - message"
        # So "AUDIT_SIGNAL | {json}"
        logger.info(f"AUDIT_SIGNAL | {json.dumps(audit_record)}")

    def assert_pair_in_whitelist(self, pair: str) -> bool:
        """
        Checks if pair is in the current whitelist.
        Returns True if safe, False (or raises) if not.
        """
        # Access DataProvider
        # self.dp is available in IStrategy
        if hasattr(self, 'dp') and self.dp:
            whitelist = self.dp.current_whitelist()
            if pair not in whitelist:
                msg = f"Security Violation: Pair {pair} is not in whitelist!"
                logger.error(msg)
                return False
        return True

    def normalize_pair(self, pair: str) -> str:
        # Just ensure uppercase and no whitespace
        return pair.upper().strip()
