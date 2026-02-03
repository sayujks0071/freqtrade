"""
AuditedStrategyMixin
Mixin class for strategies to enforce audit logging and safety checks.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
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
        # Format: AUDIT_SIGNAL | TIMESTAMP | PAIR | SIDE | REASON | CANDLE_TS | INDICATORS
        indicators_str = str(indicators_snapshot) if indicators_snapshot else "{}"

        # Use datetime.now(timezone.utc) for compatibility with Python < 3.11
        now_ts = datetime.now(timezone.utc).isoformat()  # noqa: UP017

        msg = f"AUDIT_SIGNAL | {now_ts} | {pair} | {side} | {reason} | {ts_utc} | {indicators_str}"
        logger.info(msg)

    def assert_pair_in_whitelist(self, pair: str, whitelist: list[str] | None = None) -> bool:
        """
        Assert pair is in current whitelist.
        """
        if whitelist is None:
            whitelist = self.config.get("exchange", {}).get("pair_whitelist", [])

        if whitelist and pair not in whitelist:
            logger.warning(f"AUDIT_WARNING | Pair {pair} not in whitelist but processing!")
            return False
        return True

    def normalize_pair(self, pair: str) -> str:
        """
        Normalize pair to uppercase.
        """
        # Basic normalization: uppercase
        return pair.upper()
