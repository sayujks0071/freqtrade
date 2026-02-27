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

    def log_signal(
        self,
        pair: str,
        timeframe: str,
        direction: str,
        reason: str,
        candle_date: datetime,
    ) -> None:
        """
        Log entry/exit signals to audit log.
        """
        # This logs to standard freqtrade log, but could be directed to a separate file or DB.
        # Freqtrade logs are captured.
        # Format: AUDIT_SIGNAL | TIMESTAMP | PAIR | DIRECTION | REASON | CANDLE
        msg = (
            f"AUDIT_SIGNAL | {datetime.now(UTC).isoformat()} | {pair} | "
            f"{direction} | {reason} | {candle_date}"
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

    def validate_risk_limits(self) -> None:
        """
        Enforce strict risk limits on configuration.
        """
        # Check max_open_trades
        max_trades = self.config.get("max_open_trades", float("inf"))
        # If max_trades is -1 (unlimited), it is considered > 5
        if max_trades == -1 or max_trades > 5:
            raise RuntimeError(f"RISK VIOLATION: max_open_trades ({max_trades}) cannot exceed 5.")

        # Check stoploss
        # self.stoploss is defined in the strategy class.
        stoploss = getattr(self, "stoploss", float("-inf"))

        # "Strictly looser than -10%" means < -0.10 (e.g. -0.11 is looser).
        if stoploss < -0.10:
            raise RuntimeError(
                f"RISK VIOLATION: stoploss ({stoploss}) cannot be looser than -0.10."
            )

        logger.info("AUDIT_SUCCESS | Risk limits validated successfully.")
