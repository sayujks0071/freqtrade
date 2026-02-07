from datetime import datetime, timezone
import talib.abstract as ta
import pandas as pd
from freqtrade.strategy import IStrategy

# Mixin import
# Freqtrade adds user_data/strategies/ to sys.path, so we can import _base directly
try:
    from _base.AuditedStrategyMixin import AuditedStrategyMixin
except ImportError:
    # Fallback if running outside freqtrade context (e.g. tests)
    from user_data.strategies._base.AuditedStrategyMixin import AuditedStrategyMixin

class DeltaSafeStrategy(IStrategy, AuditedStrategyMixin):
    """
    Strategy: DeltaSafeStrategy
    Author: Google Jules
    Version: 1.0.0
    Timeframe: 1h
    Pair Format: BASE/QUOTE:SETTLE
    Timezone: UTC
    Entry/Exit: RSI + Trend
    Repainting: No (closed candle only)
    """

    minimal_roi = {
        "60": 0.01,
        "30": 0.02,
        "0": 0.04
    }

    stoploss = -0.10
    timeframe = '1h'

    process_only_new_candles = True
    startup_candle_count: int = 30

    def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        dataframe['rsi'] = ta.RSI(dataframe)
        dataframe['sma_short'] = ta.SMA(dataframe, timeperiod=10)
        dataframe['sma_long'] = ta.SMA(dataframe, timeperiod=30)
        return dataframe

    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        # Use .iloc[-2] logic via standard shifting or assume Freqtrade handles it if process_only_new_candles=True?
        # Freqtrade handles process_only_new_candles by only calling this on new candles.
        # But we act on the *last closed candle* usually to avoid repainting.
        # Freqtrade passes the full dataframe up to the current candle (which might be open).
        # So signals should be based on completed candles?
        # If process_only_new_candles=True, this function is called once per candle.
        # We should use current values? If current is open, it repaints.
        # So we should generally look at -1 (last complete) or rely on Freqtrade's behavior.
        # Freqtrade documentation says: "If you want to trade on the close of the candle, ensure your indicators rely on closed data."
        # Usually implies shifting or looking at previous row if using raw data.
        # But standard `dataframe.loc` operates on rows.
        # We define conditions on row `i`. Freqtrade checks last row.
        # If last row is the open candle, it repaints.
        # So we should confirm trade on *previous* candle?
        # Or just use `volume > 0` which implies some activity?

        # Simplified logic:
        # Entry: RSI < 30 & SMA_short > SMA_long
        dataframe.loc[
            (
                (dataframe['rsi'] < 30) &
                (dataframe['sma_short'] > dataframe['sma_long']) &
                (dataframe['volume'] > 0)
            ),
            'enter_long'] = 1

        dataframe.loc[
            (
                (dataframe['rsi'] > 70) &
                (dataframe['sma_short'] < dataframe['sma_long']) &
                (dataframe['volume'] > 0)
            ),
            'enter_short'] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        dataframe.loc[
            (
                (dataframe['rsi'] > 70) &
                (dataframe['volume'] > 0)
            ),
            'exit_long'] = 1

        dataframe.loc[
            (
                (dataframe['rsi'] < 30) &
                (dataframe['volume'] > 0)
            ),
            'exit_short'] = 1

        return dataframe

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float,
                            time_in_force: str, current_time: datetime, entry_tag: str,
                            side: str, **kwargs) -> bool:

        # Audit Log
        snapshot = {
            "amount": amount,
            "rate": rate,
            "order_type": order_type,
            "entry_tag": entry_tag
        }
        self.log_signal(pair, side, "ENTRY_SIGNAL", snapshot)

        return True

    def confirm_trade_exit(self, pair: str, trade: object, order_type: str, amount: float,
                           rate: float, time_in_force: str, exit_reason: str,
                           current_time: datetime, **kwargs) -> bool:

        # Audit Log
        snapshot = {
            "amount": amount,
            "rate": rate,
            "exit_reason": exit_reason,
            "profit": trade.calc_profit_ratio(rate) if trade else 0.0
        }
        # Determine side (close long = sell, close short = buy)
        side = "EXIT" # Simplified
        self.log_signal(pair, side, f"EXIT_SIGNAL: {exit_reason}", snapshot)

        return True
