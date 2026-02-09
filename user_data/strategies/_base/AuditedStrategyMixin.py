"""
AuditedStrategyMixin
Mixin class for strategies to enforce audit logging and safety checks.
"""

import logging
import re
from datetime import datetime
from typing import Any


logger = logging.getLogger(__name__)


class AuditedStrategyMixin:
    """
    Mixin for strategies to enforce audit logging and safety checks.
    """

    # Type hint for the config attribute expected from IStrategy
    config: dict[str, Any]

    # Regex for Freqtrade/CCXT futures pair format: BASE/QUOTE:SETTLE
    # e.g., BTC/USDT:USDT
    PAIR_FORMAT_REGEX = re.compile(r"^[A-Z0-9]+/[A-Z0-9]+:[A-Z0-9]+$")

    def log_signal(
        self,
        pair: str,
        side: str,
        reason: str,
        ts_utc: datetime,
        indicators_snapshot: dict[str, Any],
    ) -> None:
        """
        Log entry/exit signals to audit log with snapshot of indicators.

        :param pair: The pair (e.g. BTC/USDT:USDT)
        :param side: 'long' or 'short'
        :param reason: The signal reason (e.g. 'rsi_low')
        :param ts_utc: The timestamp of the signal (candle open or close time)
        :param indicators_snapshot: A dict of indicator values at the time of signal
        """
        # Format snapshot as string for logging
        snapshot_str = ", ".join(f"{k}={v}" for k, v in indicators_snapshot.items())

        # Format: AUDIT_SIGNAL | TIMESTAMP | PAIR | SIDE | REASON | SNAPSHOT
        msg = f"AUDIT_SIGNAL | {ts_utc.isoformat()} | {pair} | {side} | {reason} | {snapshot_str}"
        logger.info(msg)

    def normalize_pair(self, pair: str) -> str:
        """
        Normalize pair to uppercase and validate format.

        :param pair: The pair string
        :return: Normalized pair string
        :raises ValueError: If pair format is invalid
        """
        normalized = pair.upper()
        if not self.PAIR_FORMAT_REGEX.match(normalized):
            # Log error but maybe raise?
            # The requirement says "fails fast if pair format mismatches"
            # So we raise ValueError.
            logger.error(f"AUDIT_ERROR | Invalid pair format: {pair}")
            raise ValueError(f"Invalid pair format: {pair}. Expected BASE/QUOTE:SETTLE")
        return normalized

    def assert_pair_in_whitelist(self, pair: str, whitelist: list[str]) -> None:
        """
        Assert pair is in the provided whitelist.

        :param pair: The pair to check
        :param whitelist: List of whitelisted pairs
        :raises ValueError: If pair is not in whitelist
        """
        # Normalize first? Strategy should handle normalized pairs usually.
        # But we can try to normalize before check if needed.
        # Strict check: exact match.
        if pair not in whitelist:
            logger.warning(f"AUDIT_WARNING | Pair {pair} not in whitelist!")
            raise ValueError(f"Pair {pair} is not in the active whitelist.")
