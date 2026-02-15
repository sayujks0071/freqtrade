"""
AuditedStrategyMixin Module.
Provides mixin for strategy audit logging and safety.
"""
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from freqtrade.strategy import IStrategy

logger = logging.getLogger(__name__)


class AuditedStrategyMixin:
    """
    Mixin for strategies to ensure audit logging and safety checks.
    Must be mixed into an IStrategy subclass.

    Logic must run on closed candles.
    """

    if TYPE_CHECKING:
        # Define expected attributes from IStrategy
        dp: Any
        timeframe: str

    def assert_pair_in_whitelist(self, pair: str):
        """
        Asserts that the pair is in the current whitelist.
        """
        if self.dp:
            whitelist = self.dp.current_whitelist()
            if pair not in whitelist:
                logger.warning(
                    f"AUDIT WARN: Pair {pair} is not in the active whitelist but is being traded!"
                )
                # Depending on strictness, we could raise an exception to block the trade
                # raise DependencyException(f"Pair {pair} not in whitelist")
        else:
            # Backtesting mode usually
            pass

    def log_signal(
        self,
        pair: str,
        side: str,
        reason: str,
        indicators: dict[str, Any] | None = None
    ):
        """
        Log a structured audit signal.
        Format: AUDIT_SIGNAL | UTC_TIMESTAMP | PAIR | SIDE | REASON | INDICATORS
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        # Filter indicators to avoid huge logs if passed full dict
        ind_str = str(indicators) if indicators else "{}"

        log_msg = f"AUDIT_SIGNAL | {timestamp} | {pair} | {side} | {reason} | {ind_str}"
        logger.info(log_msg)

    def confirm_trade_entry(
        self,
        pair: str,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        current_time: datetime,
        entry_tag: str,
        side: str,
        **kwargs
    ) -> bool:
        """
        Log entry signal and validate whitelist.
        """
        self.assert_pair_in_whitelist(pair)

        # Try to get indicators snapshot
        indicators = {}
        if self.dp:
            try:
                # fetch latest candle
                dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
                if not dataframe.empty:
                    last_candle = dataframe.iloc[-1].to_dict()
                    # Filter relevant indicators (e.g. rsi, macd, close)
                    keys = ['close', 'rsi', 'macd', 'volume', 'bb_lower', 'bb_upper']
                    indicators = {k: v for k, v in last_candle.items() if k in keys}
            except Exception:
                # Log exception but don't crash
                logger.warning(f"Failed to fetch indicators for {pair}", exc_info=True)

        self.log_signal(pair, side, entry_tag or "entry", indicators)
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
        **kwargs
    ) -> bool:
        """
        Log exit signal.
        """
        profit_ratio = trade.calc_profit_ratio(rate)
        indicators = {"profit_ratio": f"{profit_ratio:.4f}"}

        self.log_signal(pair, "exit", exit_reason, indicators)
        return True
