"""
AuditedStrategyMixin
Mixin class for strategies to enforce audit logging and safety checks.
"""

import logging
from datetime import datetime, timezone
from typing import Any, List, Optional


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
        indicators: dict[str, Any],
    ) -> None:
        """
        Log entry/exit signals to audit log.
        Format: AUDIT_SIGNAL | UTC_TIMESTAMP | PAIR | SIDE | REASON | SNAPSHOT
        """
        # Ensure ts_utc is timezone aware and UTC
        if ts_utc.tzinfo is None:
            ts_utc = ts_utc.replace(tzinfo=timezone.utc)

        # Serialize indicators for logging
        snapshot = str(indicators)

        msg = (
            f"AUDIT_SIGNAL | {ts_utc.isoformat()} | {pair} | "
            f"{side} | {reason} | {snapshot}"
        )
        logger.info(msg)

    def normalize_pair(self, pair: str) -> str:
        """
        Normalize pair to uppercase.
        """
        return pair.upper()

    def assert_pair_in_whitelist(self, pair: str, whitelist: List[str]) -> None:
        """
        Assert pair is in the provided whitelist.
        """
        if pair not in whitelist:
            msg = f"AUDIT_ERROR | Pair {pair} not in provided whitelist!"
            logger.error(msg)
            raise ValueError(msg)

    def validate_pair_format(self, pair: str) -> bool:
        """
        Check for symbol sanity: BASE/QUOTE:SETTLE
        """
        if "/" not in pair or ":" not in pair:
            msg = f"AUDIT_ERROR | Invalid pair format {pair}. Expected BASE/QUOTE:SETTLE"
            logger.error(msg)
            # Fail fast
            raise ValueError(msg)
        return True
