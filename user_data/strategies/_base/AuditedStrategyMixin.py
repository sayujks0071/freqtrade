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
        if indicators_snapshot is None:
            indicators_snapshot = {}

        # Format snapshot as key=value string
        snapshot_str = ", ".join(f"{k}={v}" for k, v in indicators_snapshot.items())

        # Format: AUDIT_SIGNAL | TIMESTAMP | PAIR | SIDE | REASON | INDICATORS
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
        Assert pair is in the provided whitelist.
        Raises ValueError if not found.
        """
        if pair not in whitelist:
            error_msg = f"AUDIT_ERROR | Pair {pair} not in whitelist but processing attempted!"
            logger.error(error_msg)
            raise ValueError(error_msg)
