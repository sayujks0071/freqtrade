"""
AuditedStrategyMixin
Mixin class for strategies to enforce audit logging and safety checks.
"""

import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional


logger = logging.getLogger(__name__)


class AuditedStrategyMixin:
    """
    Mixin for strategies to enforce audit logging and safety checks.
    """

    # Type hint for the config attribute expected from IStrategy
    config: dict[str, Any]
    # Type hint for the dp attribute expected from IStrategy
    dp: Any

    def log_signal(
        self,
        pair: str,
        side: str,
        reason: str,
        ts_utc: datetime,
        indicators_snapshot: Optional[dict[str, Any]] = None,  # noqa: UP045
    ) -> None:
        """
        Log entry/exit signals to audit log.
        """
        # Format: AUDIT_SIGNAL | TIMESTAMP | PAIR | SIDE | REASON | INDICATORS
        # Ensure timestamp is UTC
        if ts_utc.tzinfo is None:
            # Assume UTC if naive, but log warning? Or just replace?
            # Ideally strategies pass aware datetime.
            ts_utc = ts_utc.replace(tzinfo=timezone.utc)  # noqa: UP017

        indicators_str = str(indicators_snapshot) if indicators_snapshot else "{}"

        msg = f"AUDIT_SIGNAL | {ts_utc.isoformat()} | {pair} | {side} | {reason} | {indicators_str}"
        logger.info(msg)

    def assert_pair_in_whitelist(self, pair: str) -> None:
        """
        Assert pair is in current whitelist and follows Futures format (BASE/QUOTE:SETTLE).
        Raises ValueError if validation fails.
        """
        # Check whitelist membership
        whitelist = self.config.get("exchange", {}).get("pair_whitelist", [])
        if whitelist and pair not in whitelist:
            error_msg = f"AUDIT_ERROR | Pair {pair} not in whitelist but processing!"
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Check format for Futures: BASE/QUOTE:SETTLE
        # Regex: Anything/Anything:Anything
        if not re.match(r"^[A-Z0-9]+/[A-Z0-9]+:[A-Z0-9]+$", pair):
            error_msg = (
                f"AUDIT_ERROR | Pair {pair} does not match Futures format (BASE/QUOTE:SETTLE)!"
            )
            logger.error(error_msg)
            raise ValueError(error_msg)

    def normalize_pair(self, pair: str) -> str:
        """
        Normalize pair to uppercase.
        """
        return pair.upper()
