"""
AuditedStrategyMixin
Mixin class for strategies to enforce audit logging and safety checks.
"""

from datetime import datetime
import logging
from typing import Any

logger = logging.getLogger(__name__)


class AuditedStrategyMixin:
    """
    Mixin for strategies to enforce audit logging and safety checks.
    """

    def log_signal(
        self,
        pair: str,
        side: str,
        reason: str,
        ts_utc: datetime,
        indicators_snapshot: dict[str, Any],
    ) -> None:
        """
        Log entry/exit signals to audit log.
        Format: AUDIT_SIGNAL | UTC_TIMESTAMP | PAIR | SIDE | REASON | SNAPSHOT
        """
        snapshot_str = str(indicators_snapshot)
        msg = (
            f"AUDIT_SIGNAL | {ts_utc.isoformat()} | {pair} | "
            f"{side} | {reason} | {snapshot_str}"
        )
        logger.info(msg)

    def normalize_pair(self, pair: str) -> str:
        """
        Normalize pair to uppercase.
        """
        return pair.upper()

    def assert_pair_in_whitelist(self, pair: str, whitelist: list[str]) -> None:
        """
        Assert pair is in current whitelist. Raises ValueError if not.
        """
        if pair not in whitelist:
            raise ValueError(f"Pair {pair} is not in the whitelist!")
