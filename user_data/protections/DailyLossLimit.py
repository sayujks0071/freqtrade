from datetime import UTC, datetime, timedelta
from typing import Any

from freqtrade.protection import IProtection, ProtectionReturn

from freqtrade.persistence import Trade


class DailyLossLimit(IProtection):
    """
    Daily Loss Limit Protection.
    Stops trading for the rest of the day if realized PnL drops below a threshold.
    """

    @property
    def protection_name(self):
        return "DailyLossLimit"

    @property
    def protection_global_id(self):
        return "daily_loss_limit"

    def __init__(self, config: dict[str, Any], protection_config: dict[str, Any]) -> None:
        super().__init__(config, protection_config)
        self.daily_limit = self.protection_config.get("daily_loss_limit", 0.05)  # Default 5%

    def global_stop(self, date: datetime, pair: str, timeframe: str, **kwargs) -> ProtectionReturn:
        # Calculate start of day (UTC)
        # date is the candle open time usually, or current time depending on context.
        # Use provided date

        # Ensure date is timezone aware (UTC)
        if date.tzinfo is None:
            date = date.replace(tzinfo=UTC)

        today_start = date.replace(hour=0, minute=0, second=0, microsecond=0)

        # Get all closed trades for today
        # Trade.get_trades_proxy returns trades closed AFTER the given date if is_open=False
        trades = Trade.get_trades_proxy(is_open=False, close_date=today_start)

        daily_profit = 0.0
        for trade in trades:
            # close_profit is relative profit (e.g. 0.01 = 1%)
            # We sum up the percentages. This is a simplification but common.
            # Alternatively we could sum absolute profit and divide by current wallet balance.
            # But IProtection doesn't have easy access to wallet balance unless passed.
            # Let's stick to sum of percentages.
            daily_profit += trade.close_profit

        if daily_profit < -self.daily_limit:
            # Lock until the start of next day
            lock_until = today_start + timedelta(days=1)
            reason = f"Daily Loss Limit Reached: {daily_profit:.2%}"
            return True, lock_until, reason

        return False, None, None
