"""
AuditedStrategyMixin
Mixin class for strategies to enforce audit logging and safety checks.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional, Dict

from freqtrade.strategy import IStrategy

logger = logging.getLogger(__name__)


class AuditedStrategyMixin:
    """
    Mixin for strategies to enforce audit logging and safety checks.
    """

    # Type hints for attributes expected from IStrategy
    config: Dict[str, Any]
    dp: Any  # DataProvider

    def log_signal(
        self,
        pair: str,
        side: str,
        reason: str,
        ts_utc: datetime,
        indicators_snapshot: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Log entry/exit signals to audit log.
        Format: AUDIT_SIGNAL | UTC_TIMESTAMP | PAIR | SIDE | REASON | INDICATORS
        """
        indicators_str = str(indicators_snapshot) if indicators_snapshot else "{}"

        msg = (
            f"AUDIT_SIGNAL | {ts_utc.isoformat()} | {pair} | "
            f"{side} | {reason} | {indicators_str}"
        )
        logger.info(msg)

    def normalize_pair(self, pair: str) -> str:
        """
        Normalize pair to uppercase.
        """
        return pair.upper()

    def assert_pair_in_whitelist(self, pair: str, whitelist: Optional[list] = None) -> bool:
        """
        Assert pair is in current whitelist.
        If whitelist is not provided, tries to get it from config.
        Returns True if in whitelist, False otherwise.
        """
        if whitelist is None:
            whitelist = self.config.get("exchange", {}).get("pair_whitelist", [])

        if pair not in whitelist:
            logger.warning(f"AUDIT_WARNING | Pair {pair} not in whitelist but processing!")
            return False

        # Also check strict pair format for Delta/Futures
        # ^[A-Z0-9]+/[A-Z0-9]+:[A-Z0-9]+$
        # But maybe too strict if using regex allowlist.
        if "/" not in pair or ":" not in pair:
             logger.warning(f"AUDIT_WARNING | Pair {pair} format mismatch (expected Base/Quote:Settle)!")
             # We might want to return False here to enforce "Symbol Sanity"
             # The user asked for "symbol sanity function that fails fast"
             return False

        return True

    def _get_indicators_snapshot(self, pair: str) -> Dict[str, Any]:
        """
        Helper to fetch latest indicators for audit log.
        """
        indicators = {}
        try:
            # We need to get the dataframe for this pair/timeframe
            # self.timeframe comes from IStrategy
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            # Get the last row (closed candle usually, or current)
            last_row = dataframe.iloc[-1]

            # Select key indicators to log
            for col in ['rsi', 'volume', 'close', 'open', 'high', 'low']:
                if col in last_row:
                    indicators[col] = last_row[col]
        except Exception as e:
            logger.warning(f"Could not fetch indicators for audit log: {e}")
        return indicators

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
        """
        Called right before placing a trade.
        """
        indicators = self._get_indicators_snapshot(pair)

        self.log_signal(
            pair=pair,
            side=side,
            reason=entry_tag or "unknown",
            ts_utc=datetime.now(timezone.utc), # Log event time
            indicators_snapshot=indicators
        )
        return True

    def confirm_trade_exit(
        self,
        pair: str,
        trade: Any,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        sell_reason: str,
        current_time: datetime,
        **kwargs,
    ) -> bool:
        """
        Called right before exiting a trade.
        """
        indicators = self._get_indicators_snapshot(pair)

        # Determine side (exit long or exit short)
        # trade object has is_short attribute usually
        # But we might not have 'trade' fully populated or typed here easily.
        # Assuming standard Freqtrade Trade object
        side = "exit"
        if hasattr(trade, "is_short"):
             side = "exit_short" if trade.is_short else "exit_long"

        self.log_signal(
            pair=pair,
            side=side,
            reason=sell_reason,
            ts_utc=datetime.now(timezone.utc),
            indicators_snapshot=indicators
        )
        return True
