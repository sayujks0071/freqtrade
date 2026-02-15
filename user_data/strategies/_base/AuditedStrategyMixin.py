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
        # This logs to standard freqtrade log, but could be directed to a separate file or DB.
        # Freqtrade logs are captured.
        # Format: AUDIT_SIGNAL | TIMESTAMP | PAIR | SIDE | REASON | INDICATORS
        indicators_str = str(indicators_snapshot) if indicators_snapshot else "{}"

        # Ensure timestamp is ISO format
        ts_str = ts_utc.isoformat() if isinstance(ts_utc, datetime) else str(ts_utc)

        msg = f"AUDIT_SIGNAL | {ts_str} | {pair} | {side} | {reason} | {indicators_str}"
        logger.info(msg)

    def normalize_pair(self, pair: str) -> str:
        """
        Normalize pair to uppercase.
        """
        return pair.upper()

    def assert_pair_in_whitelist(self, pair: str, whitelist: list[str] | None = None) -> None:
        """
        Assert pair is in current whitelist. Raises ValueError if not.
        """
        if whitelist is None:
            whitelist = self.config.get("exchange", {}).get("pair_whitelist", [])

        # If whitelist is empty, maybe we shouldn't fail? Or should we?
        # Freqtrade usually has a whitelist. If it's empty, no pairs are traded.
        # But if the pair is passed here, it means the bot is trying to process it.
        # So it must be in the whitelist.

        if whitelist and pair not in whitelist:
            msg = f"AUDIT_ERROR | Pair {pair} not in whitelist!"
            logger.error(msg)
            raise ValueError(msg)
