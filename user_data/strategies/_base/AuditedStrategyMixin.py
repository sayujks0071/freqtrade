import logging
from datetime import datetime
from typing import Any, Dict, Optional

from freqtrade.strategy import IStrategy

logger = logging.getLogger(__name__)

# Mock IStrategy to allow super() calls in Mixin without runtime error if used standalone or strictly typed
# But simpler is just to rely on MRO.


class AuditedStrategyMixin:
    """
    Mixin to enforce audit logging and safety checks for strategies.
    Must be mixed into IStrategy.
    """

    # Enforce process_only_new_candles
    process_only_new_candles = True

    def log_signal(self, pair: str, side: str, reason: str, details: Dict[str, Any] = None):
        """
        Audit log for signals.
        """
        timestamp = datetime.now(datetime.UTC).isoformat()
        msg = {
            "timestamp": timestamp,
            "type": "AUDIT_SIGNAL",
            "pair": pair,
            "side": side,
            "reason": reason,
            "details": details or {},
        }
        logger.info(f"AUDIT_SIGNAL: {msg}")

    def confirm_trade_entry(
        self,
        pair: str,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        current_time: datetime,
        entry_tag: Optional[str],
        side: str,
        **kwargs,
    ) -> bool:
        self.log_signal(
            pair,
            side,
            entry_tag or "entry",
            {"amount": amount, "rate": rate, "order_type": order_type},
        )

        # Verify whitelist (safety check)
        if hasattr(self, "dp") and self.dp:
            try:
                # current_whitelist might raise error if not initialized
                whitelist = self.dp.current_whitelist()
                if pair not in whitelist:
                    logger.warning(f"Trade rejected: {pair} not in whitelist")
                    return False
            except Exception as e:
                logger.error(f"Error checking whitelist: {e}")

        # Call next in MRO (IStrategy)
        return super().confirm_trade_entry(
            pair,
            order_type,
            amount,
            rate,
            time_in_force,
            current_time,
            entry_tag,
            side,
            **kwargs,
        )

    def confirm_trade_exit(
        self,
        pair: str,
        trade,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        exit_reason: str,
        current_time: datetime,
        **kwargs,
    ) -> bool:
        # We assume 'trade' object has certain properties.
        # trade is of type 'Trade'
        # Handle sell_reason vs exit_reason if needed, but modern freqtrade uses exit_reason

        profit_pct = trade.calc_profit_ratio(rate)
        profit_abs = trade.calc_profit(rate)
        duration = (current_time - trade.open_date_utc).total_seconds()

        self.log_signal(
            pair,
            "exit",
            exit_reason,
            {
                "amount": amount,
                "rate": rate,
                "profit_pct": profit_pct,
                "profit_abs": profit_abs,
                "duration": duration,
            },
        )

        return super().confirm_trade_exit(
            pair,
            trade,
            order_type,
            amount,
            rate,
            time_in_force,
            exit_reason,
            current_time,
            **kwargs,
        )
