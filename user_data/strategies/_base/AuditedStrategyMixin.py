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

        :param pair: The pair being traded (e.g. BTC/USDT:USDT)
        :param side: 'long' or 'short'
        :param reason: Description of the signal (e.g. "RSI < 30 & Volume > 0")
        :param ts_utc: The timestamp of the signal (candle time or current time) in UTC
        :param indicators_snapshot: Dictionary of key indicator values at the time of signal
        """
        snapshot_str = str(indicators_snapshot) if indicators_snapshot else "{}"

        # Ensure ts_utc is timezone-aware
        if ts_utc.tzinfo is None:
            ts_utc = ts_utc.replace(tzinfo=UTC)

        # Format: AUDIT_SIGNAL | TIMESTAMP | PAIR | SIDE | REASON | INDICATORS
        msg = f"AUDIT_SIGNAL | {ts_utc.isoformat()} | {pair} | {side} | {reason} | {snapshot_str}"
        logger.info(msg)

    def normalize_pair(self, pair: str) -> str:
        """
        Normalize pair to uppercase.
        Add specific normalization logic if needed (e.g. stripping spaces).
        """
        return pair.upper().strip()

    def assert_pair_in_whitelist(self, pair: str, whitelist: list[str]) -> None:
        """
        Assert pair is in the provided whitelist.
        Raises ValueError if not found.
        """
        normalized_pair = self.normalize_pair(pair)
        # Normalize whitelist as well just in case
        normalized_whitelist = [self.normalize_pair(p) for p in whitelist]

        if normalized_pair not in normalized_whitelist:
            # Also try to match simple symbol if whitelist has full pairs or vice versa?
            # For now, strict match.
            # If specific format is required (e.g. BTC/USDT:USDT), exact match is best.
            raise ValueError(
                f"AUDIT_ERROR: Pair {pair} not in whitelist! Aborting signal."
            )
