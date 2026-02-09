"""
Strategy: DeltaSafeStrategy
Author: Freqtrade User
Version: 1.0
Timeframe: 5m
Source: Audited Strategy
"""
import logging
from pandas import DataFrame
from freqtrade.strategy import IStrategy, IntParameter
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib
from user_data.strategies._base.AuditedStrategyMixin import AuditedStrategyMixin

logger = logging.getLogger(__name__)

class DeltaSafeStrategy(IStrategy, AuditedStrategyMixin):
    """
    DeltaSafeStrategy - A reference strategy for Delta Exchange Futures.
    Inherits from AuditedStrategyMixin to enforce safety checks and audit logging.
    """
    INTERFACE_VERSION = 3

    # Minimal ROI designed for the strategy.
    minimal_roi = {
        "60": 0.01,
        "30": 0.02,
        "0": 0.04
    }

    # Optimal stoploss designed for the strategy.
    stoploss = -0.10

    # Trailing stop:
    trailing_stop = False

    # Run "populate_indicators" only for new candle.
    process_only_new_candles = True

    # These values can be overridden in the "ask_strategy" section in the config.
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    # Number of candles the strategy requires before producing valid signals
    startup_candle_count: int = 30

    # Optional order type mapping.
    order_types = {
        'entry': 'limit',
        'exit': 'limit',
        'stoploss': 'market',
        'stoploss_on_exchange': False
    }

    # Order time in force.
    order_time_in_force = {
        'entry': 'gtc',
        'exit': 'gtc'
    }

    # Custom Protection Parameters
    max_daily_loss_pct = 0.05  # 5% daily loss limit

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Adds several different TA indicators to the given DataFrame
        """
        # RSI
        dataframe['rsi'] = ta.RSI(dataframe)

        # ADX
        dataframe['adx'] = ta.ADX(dataframe)

        # Bollinger Bands
        bollinger = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=2)
        dataframe['bb_lowerband'] = bollinger['lower']
        dataframe['bb_middleband'] = bollinger['mid']
        dataframe['bb_upperband'] = bollinger['upper']

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Based on TA indicators, populates the entry signal for the given dataframe
        """
        dataframe.loc[
            (
                (dataframe['rsi'] < 30) &
                (dataframe['adx'] > 25) &
                (dataframe['volume'] > 0)
            ),
            'enter_long'] = 1

        dataframe.loc[
            (
                (dataframe['rsi'] > 70) &
                (dataframe['adx'] > 25) &
                (dataframe['volume'] > 0)
            ),
            'enter_short'] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Based on TA indicators, populates the exit signal for the given dataframe
        """
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
                            time_in_force: str, current_time: str, entry_tag: str,
                            side: str, **kwargs) -> bool:
        """
        Called right before placing a entry order.
        Timing for this function is critical, so avoid doing heavy processing.
        """

        # 1. Normalize Pair (Safety)
        try:
            self.normalize_pair(pair)
        except ValueError as e:
            logger.error(f"Invalid pair format: {e}")
            return False

        # 2. Check Daily Loss Limit (Risk Guardrail)
        if self.check_daily_loss_limit(self.max_daily_loss_pct):
            logger.warning(f"Trade rejected by Daily Loss Limit for {pair}")
            return False

        # 3. Log Audit Signal
        self.log_signal(pair, side, "ENTRY_SIGNAL", {"rate": rate, "amount": amount, "tag": entry_tag})

        return True

    def confirm_trade_exit(self, pair: str, trade: 'Trade', order_type: str, amount: float,
                           rate: float, time_in_force: str, exit_reason: str,
                           current_time: str, **kwargs) -> bool:
        """
        Called right before placing a exit order.
        """

        # Log Audit Signal
        self.log_signal(pair, "exit", exit_reason, {"rate": rate, "amount": amount})

        return True
