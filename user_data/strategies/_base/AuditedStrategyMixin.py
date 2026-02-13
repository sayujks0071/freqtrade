import logging
from datetime import datetime
from freqtrade.persistence import Trade

logger = logging.getLogger(__name__)

class AuditedStrategyMixin:
    """
    Mixin to enforce audit logging and safety checks for Delta Exchange strategies.
    Must be mixed in with IStrategy.
    Usage: class MyStrategy(AuditedStrategyMixin, IStrategy):
    """

    # Safety Check: Enforce closed candle processing
    process_only_new_candles = True

    def bot_start(self, **kwargs) -> None:
        """
        Called on startup. Verifies safety settings.
        """
        if not self.process_only_new_candles:
             logger.warning("AUDIT: Strategy %s does not enforce process_only_new_candles=True. This is risky for futures!", self.__class__.__name__)

        logger.info("AUDIT: Strategy %s started with AuditedStrategyMixin.", self.__class__.__name__)

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float,
                            time_in_force: str, current_time: datetime, entry_tag: str | None,
                            side: str, **kwargs) -> bool:
        """
        Audit log for trade entry.
        """
        logger.info(
            f"[AUDIT] ENTRY SIGNAL: Pair={pair}, Side={side}, Amount={amount}, Rate={rate}, "
            f"Tag={entry_tag}, Time={current_time.isoformat()}"
        )
        return True

    def confirm_trade_exit(self, pair: str, trade: Trade, order_type: str, amount: float,
                           rate: float, time_in_force: str, exit_reason: str,
                           current_time: datetime, **kwargs) -> bool:
        """
        Audit log for trade exit.
        """
        logger.info(
            f"[AUDIT] EXIT SIGNAL: Pair={pair}, Profit={trade.close_profit_abs if trade else 'N/A'}, Reason={exit_reason}, "
            f"Time={current_time.isoformat()}"
        )
        return True
