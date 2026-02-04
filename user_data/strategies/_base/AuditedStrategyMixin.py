"""
AuditedStrategyMixin
Mixin class for strategies to enforce audit logging and safety checks.
"""

import logging
from datetime import datetime
from typing import Any


logger = logging.getLogger(__name__)


class AuditedStrategyMixin:
    """
    Mixin for strategies to enforce audit logging and safety checks.
    """

    # Type hint for the config attribute expected from IStrategy
    config: dict[str, Any]

    def log_signal(
        self,
        pair: str,
        side: str,
        reason: str,
        ts_utc: datetime,
        indicators_snapshot: dict[str, Any] | None = None,
    ) -> None:
        """
        Log entry/exit signals to audit log.
        """
        # Ensure timestamp is ISO-8601
        ts_str = ts_utc.isoformat()

        snapshot_str = str(indicators_snapshot) if indicators_snapshot else "{}"

        # Format: AUDIT_SIGNAL | TIMESTAMP | PAIR | SIDE | REASON | SNAPSHOT
        msg = f"AUDIT_SIGNAL | {ts_str} | {pair} | {side} | {reason} | {snapshot_str}"
        logger.info(msg)

    def normalize_pair(self, pair: str) -> str:
        """
        Normalize pair to uppercase.
        """
        return pair.upper()

    def assert_pair_in_whitelist(self, pair: str, whitelist: list[str]) -> None:
        """
        Assert pair is in current whitelist.
        """
        normalized_pair = self.normalize_pair(pair)
        # Check against normalized whitelist just in case
        normalized_whitelist = [self.normalize_pair(p) for p in whitelist]

        if normalized_pair not in normalized_whitelist:
            msg = f"AUDIT_FAILURE | Pair {pair} not in whitelist!"
            logger.error(msg)
            raise ValueError(msg)
