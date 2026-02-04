from datetime import datetime, timezone
import logging
import os
import json
from freqtrade.strategy import IStrategy
from freqtrade.persistence import Trade

logger = logging.getLogger(__name__)

class AuditedStrategyMixin(IStrategy):
    """
    Mixin to enforce audit logging and risk controls.
    """

    def log_signal(self, pair: str, signal: str, reason: str, details: dict = None):
        """
        Structured audit log for signals.
        """
        now = datetime.now(timezone.utc).isoformat()
        log_entry = {
            "timestamp": now,
            "pair": pair,
            "signal": signal,
            "reason": reason,
            "details": details or {}
        }
        # Log to standard log
        logger.info(f"AUDIT_SIGNAL: {json.dumps(log_entry)}")

    def check_daily_loss_limit(self, current_time: datetime) -> bool:
        """
        Returns True if trading is allowed, False if daily loss limit hit.
        """
        # Read env var, default -5% (-0.05)
        limit_pct = float(os.environ.get('DAILY_LOSS_LIMIT_PCT', -0.05))

        # Get trades closed today (UTC)
        today = current_time.replace(hour=0, minute=0, second=0, microsecond=0)

        try:
            # We use the Trade query method provided by Freqtrade persistence
            trades = Trade.get_trades(query=[
                Trade.is_open.is_(False),
                Trade.close_date >= today
            ])

            # Summing the profit ratios of all trades closed
            daily_profit = sum(t.close_profit for t in trades)

            if daily_profit < limit_pct:
                logger.warning(f"RISK: Daily loss limit hit! Profit {daily_profit:.2%} < {limit_pct:.2%}")
                return False

            return True
        except Exception as e:
            logger.error(f"Error checking daily loss limit: {e}")
            return True

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float,
                            time_in_force: str, current_time: datetime, entry_tag: str,
                            side: str, **kwargs) -> bool:

        # Check daily loss
        if not self.check_daily_loss_limit(current_time):
            self.log_signal(pair, "entry_rejected", "daily_loss_limit_hit")
            return False

        # Log entry
        self.log_signal(pair, "entry_confirmed", entry_tag or "strategy_signal", {
            "side": side,
            "rate": rate,
            "amount": amount
        })

        return True

    def confirm_trade_exit(self, pair: str, trade: Trade, order_type: str, amount: float,
                           rate: float, time_in_force: str, exit_reason: str,
                           current_time: datetime, **kwargs) -> bool:

        self.log_signal(pair, "exit_confirmed", exit_reason, {
            "profit": trade.calc_profit_ratio(rate),
            "duration": (current_time - trade.open_date).total_seconds()
        })
        return True

    def leverage(self, pair: str, current_time: datetime, current_rate: float,
                 proposed_leverage: float, max_leverage: float, side: str,
                 **kwargs) -> float:
        """
        Enforce leverage cap.
        """
        # Default hard cap 2.0 or from env
        cap = float(os.environ.get('MAX_LEVERAGE', 2.0))
        return min(proposed_leverage, cap, max_leverage)
