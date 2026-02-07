"""
AuditedStrategyMixin
Mixin class for strategies to enforce audit logging and safety checks.
"""

import logging
from datetime import UTC, datetime
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
        if ts_utc.tzinfo is None:
            ts_utc = ts_utc.replace(tzinfo=UTC)

        snapshot_str = str(indicators_snapshot) if indicators_snapshot else "{}"

        # Format: AUDIT_SIGNAL | UTC_TIMESTAMP | PAIR | SIDE | REASON | SNAPSHOT
        msg = (
            f"AUDIT_SIGNAL | {ts_utc.isoformat()} | {pair} | "
            f"{side} | {reason} | {snapshot_str}"
        )
        logger.info(msg)

    def assert_pair_in_whitelist(self, pair: str, whitelist: list[str]) -> None:
        """
        Assert pair is in whitelist. Raises ValueError if not.
        """
        if pair not in whitelist:
            msg = f"AUDIT_ERROR | Pair {pair} not in whitelist!"
            logger.error(msg)
            raise ValueError(msg)

    def normalize_pair(self, pair: str) -> str:
        """
        Normalize pair to uppercase and check basic format.
        """
        pair = pair.upper()
        if "/" not in pair:
            msg = f"AUDIT_ERROR | Pair {pair} does not contain '/', invalid format for Freqtrade."
            logger.error(msg)
            raise ValueError(msg)
        return pair
