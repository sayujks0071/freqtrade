import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from freqtrade.constants import Config, LongShort
from freqtrade.persistence import Trade
from freqtrade.plugins.protections import IProtection, ProtectionReturn

logger = logging.getLogger(__name__)

class DailyLossLimit(IProtection):
    """
    Stops trading if daily realized PnL is below a certain percentage.
    """
    has_global_stop: bool = True
    has_local_stop: bool = False

    def __init__(self, config: Config, protection_config: dict[str, Any]) -> None:
        super().__init__(config, protection_config)

        # Max daily loss in percentage (e.g., 0.05 for 5%)
        self._max_daily_loss = protection_config.get("max_daily_loss", 0.05)
        self._max_daily_loss_abs = protection_config.get("max_daily_loss_abs", 0.0)

    def short_desc(self) -> str:
        return (
            f"{self.name} - Stop trading if daily loss > {self._max_daily_loss*100}%."
        )

    def _check_daily_loss(self, date_now: datetime) -> ProtectionReturn | None:
        # Calculate start of day (UTC)
        start_of_day = date_now.replace(hour=0, minute=0, second=0, microsecond=0)

        # Get closed trades for today
        trades = Trade.get_trades_proxy(is_open=False, close_date=start_of_day)

        if not trades:
            return None

        # Calculate daily realized PnL (sum of close_profit_abs)
        daily_profit_abs = sum(t.close_profit_abs for t in trades)

        # Check absolute limit if set
        if self._max_daily_loss_abs > 0 and daily_profit_abs < 0 and abs(daily_profit_abs) > self._max_daily_loss_abs:
             self.log_once(
                f"Trading stopped. Daily loss {daily_profit_abs:.2f} > {self._max_daily_loss_abs} (ABS)",
                logger.info,
            )
             until = start_of_day + timedelta(days=1)
             return ProtectionReturn(
                lock=True,
                until=until,
                reason=f"Daily Loss Limit hit (ABS): {daily_profit_abs:.2f}"
            )

        # Check percentage limit
        # Fallback to dry_run_wallet if we can't find balance.
        current_balance = self.config.get('dry_run_wallet', 1000)

        if daily_profit_abs < 0 and abs(daily_profit_abs) > (current_balance * self._max_daily_loss):
             self.log_once(
                f"Trading stopped. Daily loss {daily_profit_abs:.2f} > {self._max_daily_loss*100}% of {current_balance}",
                logger.info,
            )
             until = start_of_day + timedelta(days=1)
             return ProtectionReturn(
                lock=True,
                until=until,
                reason=f"Daily Loss Limit hit (%): {daily_profit_abs:.2f}"
            )

        return None

    def global_stop(self, date_now: datetime, side: LongShort) -> ProtectionReturn | None:
        return self._check_daily_loss(date_now)

    def stop_per_pair(self, pair: str, date_now: datetime, side: LongShort) -> ProtectionReturn | None:
        return None
