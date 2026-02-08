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
        indicators_snapshot: dict[str, Any],
    ) -> None:
        """
        Log entry/exit signals to audit log.
        """
        # Format: AUDIT_SIGNAL | UTC_TIMESTAMP | PAIR | SIDE | REASON | SNAPSHOT
        msg = (
            f"AUDIT_SIGNAL | {ts_utc.isoformat()} | {pair} | "
            f"{side} | {reason} | {indicators_snapshot}"
        )
        logger.info(msg)

    def assert_pair_in_whitelist(self, pair: str, whitelist: list[str]) -> bool:
        """
        Assert pair is in current whitelist.
        """
        if pair not in whitelist:
            logger.warning(f"AUDIT_WARNING | Pair {pair} not in whitelist but processing!")
            return False
        return True

    def normalize_pair(self, pair: str) -> str:
        """
        Normalize pair to uppercase.
        """
        return pair.upper()
