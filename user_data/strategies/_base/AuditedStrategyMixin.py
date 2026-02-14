from datetime import datetime, timezone
import logging

from freqtrade.strategy import IStrategy

logger = logging.getLogger(__name__)

class AuditedStrategyMixin:
    """
    Mixin for audited strategies.
    Provides signal logging and whitelist validation.
    """

    def audit(self, event_type, pair, msg):
        """
        Log an audit event.
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        logger.info(f"AUDIT_SIGNAL: {timestamp} | {event_type} | {pair} | {msg}")

    def assert_pair_in_whitelist(self, pair):
        """
        Verify pair is in the active whitelist.
        """
        if self.config['runmode'].value in ('live', 'dry_run'):
            # In backtesting, pair_whitelist might not be populated same way
            if pair not in self.dp.current_whitelist():
                 self.audit("ERROR", pair, "Pair not in whitelist!")
                 # raise ValueError(f"Pair {pair} not in whitelist")
                 # Returning False to prevent trade is better handled in confirm_trade_entry
                 return False
        return True

    def log_signal(self, pair, timeframe, signal_type):
        self.audit("SIGNAL", pair, f"Signal {signal_type} on {timeframe}")
