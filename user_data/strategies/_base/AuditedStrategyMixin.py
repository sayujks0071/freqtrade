"""
AuditedStrategyMixin
Mixin class for strategies to enforce audit logging and safety checks.

# Strategy Name: AuditedStrategyMixin
# Author: Freqtrade
# Version: 1.0
# Supported Timeframes: All
# Supported Pair Format: All
# Timezone Rule: UTC ISO-8601
# Entry Conditions: N/A
# Exit Conditions: N/A
# No Repainting: Only act on closed candles (N/A)
"""

from __future__ import annotations

from datetime import datetime
import logging
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
        # Format indicators for readability
        indicators_str = str(indicators_snapshot) if indicators_snapshot else "{}"

        # AUDIT_SIGNAL | TIMESTAMP | PAIR | SIDE | REASON | INDICATORS
        msg = f"AUDIT_SIGNAL | {ts_utc.isoformat()} | {pair} | {side} | {reason} | {indicators_str}"
        logger.info(msg)

    def normalize_pair(self, pair: str) -> str:
        """
        Normalize pair to uppercase.
        """
        return pair.upper()

    def assert_pair_in_whitelist(self, pair: str, whitelist: list[str] | None = None) -> bool:
        """
        Assert pair is in whitelist.
        """
        if whitelist is None:
            # Safely access config
            if hasattr(self, "config"):
                whitelist = self.config.get("exchange", {}).get("pair_whitelist", [])
            else:
                whitelist = []

        # Ensure whitelist is a list
        if not isinstance(whitelist, list):
            logger.warning("AUDIT_WARNING | Whitelist is not a list. Skipping check.")
            return True

        if pair not in whitelist:
            logger.warning(f"AUDIT_WARNING | Pair {pair} not in whitelist but processing!")
            return False
        return True

    def validate_pairs(self) -> None:
        """
        Sanity check for pair formats in whitelist.
        Should be called at startup.
        """
        if hasattr(self, "config"):
            whitelist = self.config.get("exchange", {}).get("pair_whitelist", [])
        else:
            whitelist = []

        for pair in whitelist:
            # Check for colon (Futures format)
            if ":" not in pair:
                raise ValueError(
                    f"AUDIT_ERROR | Pair {pair} does not match Futures format 'Base/Quote:Settle'. "
                    "Delta Exchange requires this format."
                )
