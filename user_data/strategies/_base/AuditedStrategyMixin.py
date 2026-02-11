"""
AuditedStrategyMixin
Mixin class for strategies to enforce audit logging and safety checks.
"""

import logging
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

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
        candle_date: datetime,
        indicators_snapshot: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Log entry/exit signals to audit log.
        Format: AUDIT_SIGNAL | TIMESTAMP | PAIR | SIDE | REASON | CANDLE | INDICATORS
        """
        indicators_str = str(indicators_snapshot) if indicators_snapshot else "{}"
        msg = (
            f"AUDIT_SIGNAL | {datetime.now(UTC).isoformat()} | {pair} | "
            f"{side} | {reason} | {candle_date} | {indicators_str}"
        )
        logger.info(msg)
        # Ensure it appears in stdout/logs
        print(msg)

    def normalize_pair(self, pair: str) -> str:
        """
        Normalize pair to uppercase.
        """
        return pair.upper()

    def assert_pair_in_whitelist(self, pair: str, whitelist: Optional[List[str]] = None) -> bool:
        """
        Assert pair is in current whitelist.
        Returns True if in whitelist, False otherwise (and logs warning).
        """
        if whitelist is None:
            whitelist = self.config.get("exchange", {}).get("pair_whitelist", [])

        if whitelist and pair not in whitelist:
            logger.warning(f"AUDIT_WARNING | Pair {pair} not in whitelist but processing!")
            return False
        return True

    def check_whitelist(self, pair: str) -> bool:
        """
        Deprecated alias for assert_pair_in_whitelist using config whitelist.
        """
        return self.assert_pair_in_whitelist(pair)
