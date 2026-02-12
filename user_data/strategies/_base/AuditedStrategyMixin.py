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
        indicators_snapshot: dict,
    ) -> None:
        """
        Log entry/exit signals to audit log.
        """
        # Format: AUDIT_SIGNAL | TIMESTAMP | PAIR | SIDE | REASON | CANDLE_TS | INDICATORS
        # indicators_snapshot should be a dict of key values relevant to the decision

        indicators_str = ", ".join(f"{k}={v}" for k, v in indicators_snapshot.items())

        msg = (
            f"AUDIT_SIGNAL | {datetime.now(UTC).isoformat()} | {pair} | "
            f"{side} | {reason} | {ts_utc} | {indicators_str}"
        )
        logger.info(msg)

    def normalize_pair(self, pair: str) -> str:
        """
        Normalize pair to uppercase.
        """
        return pair.upper()

    def assert_pair_in_whitelist(self, pair: str, whitelist: list[str]) -> bool:
        """
        Assert pair is in the provided whitelist.
        """
        normalized_pair = self.normalize_pair(pair)
        # We assume whitelist is already normalized or we normalize it too?
        # Usually whitelist from freqtrade is clean.

        if normalized_pair not in whitelist:
            logger.warning(f"AUDIT_WARNING | Pair {pair} not in whitelist but processing!")
            return False
        return True
