import logging
import datetime
from typing import List, Any
from freqtrade.strategy import IStrategy

logger = logging.getLogger(__name__)

class AuditedStrategyMixin:
    """
    Mixin to add audit logging and safety checks to strategies.
    """

    def log_signal(self, pair: str, side: str, reason: str, ts_utc: datetime.datetime, indicators_snapshot: dict):
        """
        Logs a trade signal with structured data for auditing.
        """
        log_msg = (
            f"AUDIT_SIGNAL: timestamp={ts_utc.isoformat()} "
            f"pair={pair} side={side} reason='{reason}' "
            f"indicators={indicators_snapshot}"
        )
        logger.info(log_msg)
        print(log_msg) # Ensure it prints to stdout for dry-run visibility

    def normalize_pair(self, pair: str) -> str:
        """
        Validates pair format. Returns the pair.
        Warns if it doesn't look like Freqtrade pair (Base/Quote:Settle) or simple BaseQuote.
        """
        if '/' not in pair and ':' not in pair:
            # Could be Delta format e.g. BTCUSDT
            pass
        elif pair.count('/') == 1 and pair.count(':') <= 1:
             # Standard Freqtrade format
             pass
        else:
             logger.warning(f"Pair {pair} has unusual format.")

        return pair

    def assert_pair_in_whitelist(self, pair: str, whitelist: List[str]):
        """
        Ensures the pair is in the provided whitelist.
        """
        if pair not in whitelist:
            raise ValueError(f"Pair {pair} is not in the whitelist!")

    def is_live_or_dry(self) -> bool:
        """
        Checks if the bot is running in live or dry_run mode.
        """
        if hasattr(self, 'dp') and self.dp:
             return self.dp.runmode.value in ('live', 'dry_run')
        return False
