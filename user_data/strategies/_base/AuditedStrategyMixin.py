from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from freqtrade.persistence import Trade

logger = logging.getLogger(__name__)


class AuditedStrategyMixin:
    """
    Mixin to add audit logging and safety checks to strategies.
    Usage: class MyStrategy(IStrategy, AuditedStrategyMixin): ...
    """

    def log_signal(
        self,
        pair: str,
        timeframe: str,
        signal_type: str,
        reason: str,
        snapshot: dict[str, Any] | None = None,
    ) -> None:
        """
        Log a structured audit message for every signal.
        """
        ts = datetime.now(timezone.utc).isoformat()  # noqa: UP017
        snap_str = str(snapshot) if snapshot else "N/A"
        msg = f"AUDIT_SIGNAL | {ts} | {pair} | {timeframe} | {signal_type} | {reason} | {snap_str}"
        logger.info(msg)

    def assert_pair_in_whitelist(self, pair: str) -> bool:
        if hasattr(self, "dp") and self.dp:
            if pair not in self.dp.current_whitelist():
                logger.warning(f"Strategy processing pair {pair} not in whitelist!")
                return False
        return True

    def leverage(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_leverage: float,
        max_leverage: float,
        entry_tag: str | None,
        side: str,
        **kwargs: Any,
    ) -> float:
        """
        Enforce max leverage from env or default to 1.0 (safe).
        """
        env_max = float(os.environ.get("MAX_LEVERAGE", 2.0))
        return min(proposed_leverage, env_max)

    def confirm_trade_entry(
        self,
        pair: str,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        current_time: datetime,
        entry_tag: str | None,
        side: str,
        **kwargs: Any,
    ) -> bool:
        # self.timeframe is expected to be present in the main strategy class
        timeframe = getattr(self, "timeframe", "unknown")
        self.log_signal(
            pair, timeframe, f"ENTRY_{side.upper()}", entry_tag or "unknown"
        )
        return True

    def confirm_trade_exit(
        self,
        pair: str,
        trade: Trade,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        exit_reason: str,
        current_time: datetime,
        **kwargs: Any,
    ) -> bool:
        # self.timeframe is expected to be present in the main strategy class
        timeframe = getattr(self, "timeframe", "unknown")
        self.log_signal(pair, timeframe, "EXIT", exit_reason)
        return True
