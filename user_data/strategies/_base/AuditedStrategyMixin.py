"""
Strategy: AuditedStrategyMixin
Author: Freqtrade User
Version: 1.0
Timeframe: 1h
Pair Format: BASE/QUOTE:SETTLE
Timezone: UTC
Entry/Exit: Limit/Limit
Repainting: No (Closed candle only)

Mixin class for strategies to enforce audit logging and safety checks.
"""

import logging
import os
from datetime import UTC, datetime
from typing import Any

from freqtrade.persistence import Trade


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
        snapshot: dict[str, Any] | None = None,
    ) -> None:
        """
        Log entry/exit signals to audit log.
        """
        # Format: AUDIT_SIGNAL | TIMESTAMP | PAIR | DIRECTION | REASON | CANDLE | SNAPSHOT
        snap_str = str(snapshot) if snapshot else "{}"
        msg = (
            f"AUDIT_SIGNAL | {datetime.now(UTC).isoformat()} | {pair} | "
            f"{direction} | {reason} | {candle_date} | {snap_str}"
        )
        logger.info(msg)

    def check_whitelist(self, pair: str) -> bool:
        """
        Assert pair is in current whitelist.
        """
        if self.config.get("exchange", {}).get("pair_whitelist"):
            if pair not in self.config["exchange"]["pair_whitelist"]:
                logger.warning(
                    f"AUDIT_WARNING | Pair {pair} not in whitelist but processing!"
                )
                return False
        return True

    def normalize_pair(self, pair: str) -> str:
        """
        Normalize pair to uppercase.
        """
        return pair.upper()

    def check_daily_loss_limit(self, current_time: datetime) -> bool:
        """
        Check if daily loss limit is hit. Returns False if limit reached (block trade).
        """
        try:
            # Get limit from env (default 5%)
            max_daily_loss_pct = float(os.environ.get("MAX_DAILY_LOSS_PCT", 5.0))

            # Calculate start of day (UTC)
            # current_time is usually timezone aware (UTC) in freqtrade
            if current_time.tzinfo is None:
                current_time = current_time.replace(tzinfo=UTC)

            start_of_day = current_time.replace(
                hour=0, minute=0, second=0, microsecond=0
            )

            # Query closed trades for today
            # Trade.get_trades expects a list of filters
            trades = Trade.get_trades(
                [Trade.is_open.is_(False), Trade.close_date >= start_of_day]
            ).all()

            # Fix for mypy: 'float | None'. Handle None as 0.0
            daily_profit = sum((t.close_profit_abs or 0.0) for t in trades)

            # Total balance
            if not hasattr(self, "wallets"):
                logger.warning(
                    "AUDIT_PROTECTION | self.wallets not found. Skipping daily loss check."
                )
                return True

            total_balance = self.wallets.get_total_stake_amount()

            # Limit check
            loss_limit_abs = total_balance * (max_daily_loss_pct / 100.0)

            if daily_profit < -loss_limit_abs:
                logger.warning(
                    f"AUDIT_PROTECTION | Daily Loss Limit Hit! PnL: {daily_profit:.2f} "
                    f"< -{loss_limit_abs:.2f}. Blocking entry."
                )
                return False

            return True
        except Exception as e:
            logger.error(f"AUDIT_ERROR | Failed to check daily loss: {e}")
            # Fail safe? If error, maybe block or allow.
            # Allowing to prevent bot stall, but logging error.
            return True
