"""
AuditedStrategyMixin
Mixin class for strategies to enforce audit logging and safety checks.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any

from freqtrade.persistence import Trade

# from freqtrade.strategy import IStrategy
# avoiding circular import if possible, but type hint needs it?
# Just type checking.

logger = logging.getLogger(__name__)


class AuditedStrategyMixin:
    """
    Mixin for strategies to enforce audit logging and safety checks.
    Must be mixed with IStrategy.
    """

    # Type hint for the config attribute expected from IStrategy
    config: dict[str, Any]
    dp: Any  # DataProvider
    wallets: Any  # Wallets

    def log_signal(
        self,
        pair: str,
        timeframe: str,
        direction: str,
        reason: str,
        candle_date: datetime,
        indicators: dict | None = None,
    ) -> None:
        """
        Log entry/exit signals to audit log with strict formatting.
        Format: AUDIT_SIGNAL | UTC_TIMESTAMP | PAIR | SIDE | REASON | INDICATORS
        """
        indicator_str = str(indicators) if indicators else "{}"
        # Ensure UTC timestamp
        now_utc = datetime.now(timezone.utc).isoformat()

        # Format candle date to ISO string if it's datetime
        candle_str = (
            candle_date.isoformat() if isinstance(candle_date, datetime) else str(candle_date)
        )

        msg = (
            f"AUDIT_SIGNAL | {now_utc} | {pair} | "
            f"{direction} | {reason} | {candle_str} | {indicator_str}"
        )
        logger.info(msg)

    def assert_pair_in_whitelist(self, pair: str) -> bool:
        """
        Assert pair is in current whitelist.
        Returns True if safe, False if not allowed (should block trade).
        """
        # If whitelist is empty, we assume dynamic or allow all? No, strict whitelist.
        # But config whitelist might be dynamic.
        # Freqtrade handles pair validation, but this is an extra audit check.
        # We check self.config['exchange']['pair_whitelist'] if available.
        # But strategy runs on pairs in whitelist. So checking config is redundant
        # unless config changes?
        # Safe to check.
        whitelist = self.config.get("exchange", {}).get("pair_whitelist", [])
        if whitelist and pair not in whitelist:
            logger.warning(
                f"AUDIT_WARNING | Pair {pair} not in config whitelist but processing! BLOCKING."
            )
            return False
        return True

    def normalize_pair(self, pair: str) -> str:
        """
        Normalize pair to uppercase and ensure correct format for logging.
        """
        return pair.upper()

    def check_daily_loss_limit(self, current_time: datetime) -> bool:
        """
        Check if realized daily loss exceeds limit.
        Returns False if trading should be stopped for the day.
        """
        try:
            # Get limit from env (default -5% = -0.05)
            # If positive, it's disabled or misconfigured.
            limit_str = os.environ.get("DAILY_LOSS_LIMIT_PCT", "-0.05")
            daily_loss_pct = float(limit_str)

            if daily_loss_pct >= 0:
                # Disabled or misconfigured (positive limit implies profit target?)
                return True

            # Calculate start of day (UTC)
            today_start = current_time.replace(hour=0, minute=0, second=0, microsecond=0)

            # Query trades closed today
            # Use Trade.get_trades helper but filter by close_date manually in python or query
            # Trade.get_trades returns a query object? No, list of Trade objects usually
            # in recent versions
            # OR a query object in older versions.
            # In stable/develop freqtrade: Trade.get_trades(filters).all()

            trades = Trade.get_trades(
                [Trade.is_open.is_(False), Trade.close_date >= today_start]
            ).all()

            daily_pnl_abs = 0.0
            for trade in trades:
                # Double check close date just in case
                if trade.close_date and trade.close_date >= today_start:
                    daily_pnl_abs += trade.close_profit_abs  # Realized PnL in stake currency

            # Get current total balance (stake currency)
            total_balance = self.wallets.get_total_stake_amount()

            if total_balance <= 0:
                # Should have stopped before this, but safety check
                logger.error("AUDIT_CRITICAL | Total balance <= 0! Stopping.")
                return False

            # Current PnL % relative to balance
            # If balance is 1000, PnL is -50, ratio is -0.05 (-5%)
            pnl_pct = daily_pnl_abs / total_balance

            if pnl_pct < daily_loss_pct:
                logger.warning(
                    f"AUDIT_RISK | DAILY LOSS LIMIT HIT! "
                    f"PnL: {daily_pnl_abs:.2f} ({pnl_pct:.2%}) < Limit: {daily_loss_pct:.2%}. "
                    f"Stopping new entries for today."
                )
                return False

            return True

        except Exception as e:
            logger.error(f"AUDIT_ERROR | Failed to check daily loss limit: {e}")
            # Fail open to prevent lockup, but log error
            return True
