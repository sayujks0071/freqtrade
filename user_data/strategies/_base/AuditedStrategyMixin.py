"""
AuditedStrategyMixin
Mixin class for strategies to enforce audit logging and safety checks.
"""
import logging
from datetime import timezone, datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class AuditedStrategyMixin:
    """
    Mixin for strategies to enforce audit logging and safety checks.
    """
    # Type hint for the config attribute expected from IStrategy
    config: Dict[str, Any]

    def log_signal(
        self,
        pair: str,
        side: str,
        reason: str,
        ts_utc: datetime,
        indicators_snapshot: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log entry/exit signals to audit log.

        :param pair: The trading pair.
        :param side: 'long' or 'short' (and entry/exit distinction if needed).
        :param reason: The textual reason or condition that fired.
        :param ts_utc: The candle timestamp (UTC).
        :param indicators_snapshot: Dictionary of key indicator values.
        """
        # Format: AUDIT_SIGNAL | EVENT_TS | PAIR | SIDE | REASON | CANDLE_TS | INDICATORS

        event_ts = datetime.now(timezone.utc).isoformat()
        indicators_str = str(indicators_snapshot) if indicators_snapshot else "{}"

        msg = (
            f"AUDIT_SIGNAL | {event_ts} | {pair} | "
            f"{side} | {reason} | {ts_utc} | {indicators_str}"
        )
        logger.info(msg)

    def normalize_pair(self, pair: str) -> str:
        """
        Normalize pair string and check format.
        Ensures uppercase and basic structure.
        Raises ValueError if format is invalid to ensure 'fail fast'.
        """
        p = pair.upper()
        # Basic check for Futures format: BASE/QUOTE:SETTLE
        if "/" not in p:
             raise ValueError(f"AUDIT_ERROR | Pair {pair} missing separator '/'")

        return p

    def assert_pair_in_whitelist(self, pair: str, whitelist: List[str]) -> bool:
        """
        Assert pair is in the provided whitelist.
        """
        try:
            norm_pair = self.normalize_pair(pair)
            norm_whitelist = [self.normalize_pair(wp) for wp in whitelist]
        except ValueError as e:
            logger.error(f"AUDIT_ERROR | Pair normalization failed: {e}")
            return False

        if norm_pair not in norm_whitelist:
            logger.warning(f"AUDIT_WARNING | Pair {pair} not in whitelist but processing!")
            return False
        return True

    def check_whitelist(self, pair: str) -> bool:
        """
        Legacy wrapper for assert_pair_in_whitelist using self.config
        """
        if self.config.get("exchange", {}).get("pair_whitelist"):
             return self.assert_pair_in_whitelist(pair, self.config["exchange"]["pair_whitelist"])
        return True
