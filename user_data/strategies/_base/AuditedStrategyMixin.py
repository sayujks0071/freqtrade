"""
AuditedStrategyMixin
Mixin class for strategies to enforce audit logging and safety checks.
"""

import logging
from datetime import UTC, datetime
from typing import Any


logger = logging.getLogger(__name__)


class AuditedStrategyMixin:
    """
    Mixin for strategies to enforce audit logging and safety checks.
    """

    # Type hint for the config attribute expected from IStrategy
    config: dict[str, Any]
    dp: Any  # DataProvider
    timeframe: str

    def log_signal(
        self,
        pair: str,
        timeframe: str,
        direction: str,
        reason: str,
        candle_date: datetime,
        snapshot: dict | None = None,
    ) -> None:
        """
        Log entry/exit signals to audit log.
        """
        snapshot_str = str(snapshot) if snapshot else "N/A"
        msg = (
            f"AUDIT_SIGNAL | {datetime.now(UTC).isoformat()} | {pair} | "
            f"{direction} | {reason} | Candle: {candle_date} | "
            f"Snapshot: {snapshot_str}"
        )
        logger.info(msg)

    def check_whitelist(self, pair: str) -> bool:
        """
        Assert pair is in current whitelist.
        """
        if self.config.get("exchange", {}).get("pair_whitelist"):
            if pair not in self.config["exchange"]["pair_whitelist"]:
                logger.warning(f"AUDIT_WARNING | Pair {pair} not in whitelist but processing!")
                return False
        return True

    def normalize_pair(self, pair: str) -> str:
        """
        Normalize pair to uppercase.
        """
        return pair.upper()

    # Override confirm_trade_entry to hook into logging
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
        **kwargs,
    ) -> bool:
        # Get latest candle for snapshot
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        last_candle = dataframe.iloc[-1].to_dict() if not dataframe.empty else {}

        # Snapshot key indicators (RSI, etc. - generic fallback)
        snapshot = {k: v for k, v in last_candle.items() if k in ["rsi", "close", "volume", "adx"]}

        self.log_signal(pair, self.timeframe, side, entry_tag or "entry", current_time, snapshot)

        return True

    def confirm_trade_exit(
        self,
        pair: str,
        trade: Any,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        exit_reason: str,
        current_time: datetime,
        **kwargs,
    ) -> bool:
        # Snapshot
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        last_candle = dataframe.iloc[-1].to_dict() if not dataframe.empty else {}
        snapshot = {k: v for k, v in last_candle.items() if k in ["rsi", "close", "volume", "adx"]}

        self.log_signal(pair, self.timeframe, "exit", exit_reason, current_time, snapshot)

        return True
