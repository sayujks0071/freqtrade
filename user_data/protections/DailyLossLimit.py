import logging
import os
from datetime import datetime, timedelta, timezone

from freqtrade.persistence import Trade
from freqtrade.protection import IProtection


logger = logging.getLogger(__name__)


class DailyLossLimit(IProtection):
    @property
    def protection_name(self):
        return "DailyLossLimit"

    def global_stop(self, date: datetime, **kwargs) -> tuple[bool, datetime, str]:
        # Get limit from env or config
        limit_ratio = float(os.environ.get("DAILY_LOSS_LIMIT", 0.05))

        if date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)

        start_of_day = datetime.combine(date.date(), datetime.min.time(), tzinfo=timezone.utc)

        trades: list[Trade] = []
        try:
            # Efficient query using SQLAlchemy filters via Trade.get_trades
            # Converting to list to unify types with exception block
            query_res = Trade.get_trades(
                [Trade.is_open.is_(False), Trade.close_date >= start_of_day]
            )
            # Depending on Freqtrade version, this might be a list or ScalarResult
            trades = list(query_res)
        except Exception as e:
            # Fallback if filters fail (e.g. in older versions or backtesting)
            logger.warning(f"Error querying trades with filter, falling back to proxy: {e}")
            all_closed = Trade.get_trades_proxy(is_open=False)
            trades = [t for t in all_closed if t.close_date and t.close_date >= start_of_day]

        if not trades:
            return False, date, ""

        # Calculate PnL. Ensure close_profit is not None (it shouldn't be for closed trades)
        total_pnl = sum((t.close_profit or 0.0) * t.stake_amount for t in trades)

        stake_currency = self.config.get("stake_currency", "USDT")
        # self.wallets might be None in backtesting sometimes
        if self.wallets:
            total_balance = self.wallets.get_total(stake_currency)
        else:
            total_balance = 0.0  # Cannot calculate limit

        if total_balance == 0:
            return False, date, ""

        if total_pnl < 0:
            starting_balance = total_balance + abs(total_pnl)
            loss_ratio = abs(total_pnl) / starting_balance

            if loss_ratio > limit_ratio:
                next_day = start_of_day + timedelta(days=1)
                logger.warning(
                    f"Daily Loss Limit hit! PnL: {total_pnl:.2f}, Ratio: {loss_ratio:.2%}"
                )
                # Return True (stop), until next_day, reason
                return True, next_day, "Daily Loss Limit Reached"

        return False, date, ""
