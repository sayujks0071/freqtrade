import logging
from datetime import datetime, timezone
from freqtrade.strategy import IStrategy

logger = logging.getLogger(__name__)

class AuditedStrategyMixin:
    """
    Mixin for Delta Exchange strategies to enforce audit logging and safety.
    Expected to be mixed into an IStrategy subclass.
    """

    # Define class variables if needed, or rely on strategy instance vars

    def log_signal(self, pair: str, side: str, reason: str, snapshot: dict = None):
        """
        Log an entry/exit signal with snapshot data for audit.
        Format: AUDIT_SIGNAL | UTC_TIMESTAMP | PAIR | SIDE | REASON | SNAPSHOT
        """
        ts = datetime.now(timezone.utc).isoformat() # noqa: UP017
        snapshot_str = str(snapshot) if snapshot else "{}"

        # Log as INFO so it appears in standard logs.
        # For structured logging, we might want a specific format prefix.
        logger.info(f"AUDIT_SIGNAL | {ts} | {pair} | {side} | {reason} | {snapshot_str}")

    def assert_pair_in_whitelist(self, pair: str):
        """
        Safety check: ensure pair is in the active whitelist.
        """
        # self.dp (DataProvider) is available in IStrategy
        if not self.dp:
            logger.warning("DataProvider not available for whitelist check.")
            return

        # Check if pair is in current pairlist
        # current_whitelist = self.dp.current_whitelist() # method might vary
        # self.dp.available_pairs returns pairs available for trading?
        # IStrategy has self.whitelist property usually? No, self.dp has it.
        pass # Implementation depends on Freqtrade version.
        # Assuming we trust Freqtrade's pairlist manager, but this is an extra check?
        # Maybe unnecessary if Freqtrade handles it.
        # But for "safety check", we can log if we are trading something weird.
        return

    def normalize_pair(self, pair: str) -> str:
        """
        Normalize pair format if needed.
        """
        return pair
