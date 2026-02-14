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
        Format: AUDIT_SIGNAL | UTC_TIMESTAMP | PAIR | SIDE | REASON | INDICATORS
        """
        if indicators_snapshot is None:
            indicators_snapshot = {}

        # Format indicators as key=value string
        indicators_str = ", ".join(f"{k}={v}" for k, v in indicators_snapshot.items())

        msg = (
            f"AUDIT_SIGNAL | {ts_utc.isoformat()} | {pair} | {side} | {reason} | "
            f"{indicators_str}"
        )
        logger.info(msg)

    def normalize_pair(self, pair: str) -> str:
        """
        Normalize pair to uppercase.
        """
        return pair.upper()

    def assert_pair_in_whitelist(self, pair: str) -> None:
        """
        Assert pair is in current whitelist.
        Raises ValueError if not in whitelist.
        """
        whitelist = self.config.get("exchange", {}).get("pair_whitelist", [])
        if not whitelist:
            # If whitelist is empty or not found, we might warn but maybe it's dynamic
            logger.warning("AUDIT_WARNING | Pair whitelist not found in config.")
            return

        if pair not in whitelist:
            msg = f"AUDIT_FAIL | Pair {pair} not in whitelist!"
            logger.error(msg)
            # We raise error to fail fast as per requirement
            # "Any symbol mismatch causes a clear startup failure"
            # Although this is runtime check.
            # The prompt says "symbol sanity function that fails fast".
            # This is that function.
            raise ValueError(msg)
