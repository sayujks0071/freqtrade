from datetime import datetime, timedelta, timezone
from freqtrade.protection import IProtection
from freqtrade.persistence import Trade
import logging
import os
import sqlalchemy

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

        try:
            # Efficient query using SQLAlchemy filters via Trade.get_trades
            trades = Trade.get_trades([
                Trade.is_open.is_(False),
                Trade.close_date >= start_of_day
            ])
        except Exception as e:
            # Fallback if filters fail (e.g. in older versions or backtesting)
            # In backtesting, get_trades might return list of dicts or objects depending on mode
            logger.warning(f"Error querying trades with filter, falling back to proxy: {e}")
            trades = Trade.get_trades_proxy(is_open=False)
            trades = [t for t in trades if t.close_date and t.close_date >= start_of_day]

        if not trades:
            return False, date, ""

        total_pnl = sum(t.close_profit * t.stake_amount for t in trades)

        stake_currency = self.config.get('stake_currency', 'USDT')
        # self.wallets might be None in backtesting sometimes
        if self.wallets:
            total_balance = self.wallets.get_total(stake_currency)
        else:
            total_balance = 0 # Cannot calculate limit

        if total_balance == 0:
            return False, date, ""

        if total_pnl < 0:
            starting_balance = total_balance + abs(total_pnl)
            loss_ratio = abs(total_pnl) / starting_balance

            if loss_ratio > limit_ratio:
                next_day = start_of_day + timedelta(days=1)
                logger.warning(f"Daily Loss Limit hit! PnL: {total_pnl:.2f}, Ratio: {loss_ratio:.2%}")
                # Return True (stop), until next_day, reason
                return True, next_day, "Daily Loss Limit Reached"

        return False, date, ""
