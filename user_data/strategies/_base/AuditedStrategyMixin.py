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
        timeframe: str,
        direction: str,
        reason: str,
        candle_date: datetime,
        indicators_snapshot: dict[str, Any] | None = None,
    ) -> None:
        """
        Log entry/exit signals to audit log.
        """
        # This logs to standard freqtrade log, but could be directed to a separate file or DB.
        # Freqtrade logs are captured.
        # Format: AUDIT_SIGNAL | TIMESTAMP | PAIR | DIRECTION | REASON | CANDLE | SNAPSHOT

        snapshot_str = str(indicators_snapshot) if indicators_snapshot else "{}"

        msg = (
            f"AUDIT_SIGNAL | {datetime.now(UTC).isoformat()} | {pair} | "
            f"{direction} | {reason} | {candle_date} | {snapshot_str}"
        )
        logger.info(msg)

    def check_whitelist(self, pair: str) -> bool:
        """
        Assert pair is in current whitelist (from config).
        """
        if self.config.get("exchange", {}).get("pair_whitelist"):
            whitelist = self.config["exchange"]["pair_whitelist"]
            if pair not in whitelist:
                logger.warning(f"AUDIT_WARNING | Pair {pair} not in whitelist but processing!")
                return False
        return True

    def assert_pair_in_whitelist(self, pair: str, whitelist: list[str]) -> None:
        """
        Assert pair is in the provided whitelist.
        """
        if pair not in whitelist:
             raise ValueError(f"Pair {pair} is not in the allowed whitelist!")

    def normalize_pair(self, pair: str) -> str:
        """
        Normalize pair to uppercase and ensure basic format compliance.
        """
        p = pair.upper()
        # Basic check for whitespace
        if " " in p:
             raise ValueError(f"Invalid pair format (whitespace): {p}")
        return p
