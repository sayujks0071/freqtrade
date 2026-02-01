"""
MatrixAgentStrategy - FreqTrade Strategy Integration
=====================================================
FreqTrade strategy that integrates Matrix Agent signals.

This strategy uses the Matrix Agent 8-layer system to:
1. Analyze market conditions
2. Generate trade signals
3. Manage risk and position sizing
4. Execute trades based on SFP patterns

Usage:
    1. Copy this file to your FreqTrade strategies directory
    2. Update config.json to use this strategy
    3. Restart FreqTrade

Author: Matrix Agent
Version: 1.0.0
"""

import numpy as np
import pandas as pd
from pandas import DataFrame
from typing import Optional, Union
from datetime import datetime
import logging

from freqtrade.strategy import (
    IStrategy,
    Trade,
    Order,
    PairLocks,
    informative,
    stoploss_from_absolute,
    stoploss_from_open,
    merge_informative_pair,
)

from matrix_agent.core import (
    MatrixAgent,
    SFPDetector,
    MacroGatekeeper,
    SignalConverter
)

logger = logging.getLogger(__name__)


class MatrixAgentStrategy(IStrategy):
    """
    FreqTrade Strategy using Matrix Agent Analysis
    
    This strategy integrates the complete Matrix Agent system into FreqTrade,
    providing:
    - SFP-based entry signals
    - Macro-confirmed trends
    - Anti-consensus filtering
    - Risk-managed position sizing
    """
    
    # Strategy Interface Version
    INTERFACE_VERSION = 3
    
    # Can this strategy go short?
    can_short: bool = False
    
    # Minimal ROI - Matrix Agent manages this
    minimal_roi = {
        "0": 0.01,    # Take profit at 1% immediately
        "60": 0.02,   # 2% by 1 hour
        "120": 0.03,  # 3% by 2 hours
        "240": 0.05,  # 5% by 4 hours
    }
    
    # Optimal stoploss
    stoploss = -0.10
    
    # Trailing stoploss
    trailing_stop = False
    trailing_only_offset_is_reached = False
    trailing_stop_positive = 0.01
    trailing_stop_positive_offset = 0.0
    
    # Optimal timeframe
    timeframe = "5m"
    
    # Process only new candles
    process_only_new_candles = True
    
    # Use exit signals
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False
    
    # Startup candle count
    startup_candle_count: int = 200
    
    # Order types
    order_types = {
        "entry": "limit",
        "exit": "limit",
        "stoploss": "market",
        "stoploss_on_exchange": False,
    }
    
    # Order time in force
    order_time_in_force = {
        "entry": "GTC",
        "exit": "GTC"
    }
    
    # Plot configuration
    plot_config = {
        "main_plot": {
            "tema": {},
            "sar": {"color": "white"},
        },
        "subplots": {
            "RSI": {
                "rsi": {"color": "red"},
            },
            "MACD": {
                "macd": {"color": "blue"},
                "macdsignal": {"color": "orange"},
            },
        },
    }
    
    def __init__(self, config: dict = None):
        """
        Initialize strategy with Matrix Agent components.
        
        Args:
            config: Strategy configuration
        """
        super().__init__(config)
        
        # Initialize Matrix Agent
        self.matrix_agent = MatrixAgent()
        
        # Initialize signal converter
        self.signal_converter = SignalConverter()
        
        # Cache for analysis results
        self._analysis_cache = {}
        self._cache_ttl = 300  # 5 minutes
        
        logger.info("MatrixAgentStrategy initialized")
    
    def informative_pairs(self):
        """
        Define informative pair/interval combinations.
        
        Returns:
            List of (pair, interval) tuples
        """
        return [
            ("BTC/USDT", "5m"),
            ("BTC/USDT", "15m"),
            ("BTC/USDT", "1h"),
            ("BTC/USDT", "4h"),
            ("ETH/USDT", "5m"),
            ("ETH/USDT", "1h"),
            ("SOL/USDT", "5m"),
            ("SOL/USDT", "1h"),
        ]
    
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Populate indicators for the strategy.
        
        Args:
            dataframe: Dataframe with data
            metadata: Pair metadata
            
        Returns:
            DataFrame with indicators
        """
        pair = metadata['pair']
        
        # Standard indicators
        dataframe['rsi'] = self.calculate_rsi(dataframe['close'])
        dataframe['ema_9'] = self.calculate_ema(dataframe['close'], 9)
        dataframe['ema_21'] = self.calculate_ema(dataframe['close'], 21)
        dataframe['ema_50'] = self.calculate_ema(dataframe['close'], 50)
        
        # Bollinger Bands
        bb = self.calculate_bollinger_bands(dataframe['close'])
        dataframe['bb_upper'] = bb['upper']
        dataframe['bb_lower'] = bb['lower']
        dataframe['bb_middle'] = bb['middle']
        
        # MACD
        macd = self.calculate_macd(dataframe['close'])
        dataframe['macd'] = macd['macd']
        dataframe['macdsignal'] = macd['signal']
        dataframe['macdhist'] = macd['hist']
        
        # Matrix Agent Analysis
        matrix_analysis = self._get_matrix_analysis(dataframe, pair)
        
        if matrix_analysis:
            dataframe['matrix_signal'] = matrix_analysis.get('signal_strength', 0)
            dataframe['matrix_expected_r'] = matrix_analysis.get('expected_r', 0)
            dataframe['matrix_approved'] = matrix_analysis.get('approved', 0)
            dataframe['sfp_detected'] = matrix_analysis.get('sfp_detected', 0)
            dataframe['macro_approved'] = matrix_analysis.get('macro_approved', 0)
        
        return dataframe
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Populate entry signals.
        
        Args:
            dataframe: Dataframe with data
            metadata: Pair metadata
            
        Returns:
            DataFrame with entry signals
        """
        pair = metadata['pair']
        
        # Get Matrix Agent analysis
        matrix_analysis = self._get_matrix_analysis(dataframe, pair)
        
        # Default: no entry
        dataframe['enter_long'] = 0
        dataframe['enter_short'] = 0
        
        if matrix_analysis and matrix_analysis.get('approved', False):
            signal_strength = matrix_analysis.get('signal_strength', 0)
            sfp_type = matrix_analysis.get('sfp_type', None)
            
            # Strong Matrix Agent signal
            if signal_strength >= 0.7:
                if sfp_type == 'bullish_sfp':
                    dataframe.loc[
                        (dataframe['matrix_approved'] == 1) &
                        (dataframe['rsi'] < 50) &
                        (dataframe['close'] > dataframe['bb_lower']),
                        'enter_long'
                    ] = 1
                elif sfp_type == 'bearish_sfp':
                    dataframe.loc[
                        (dataframe['matrix_approved'] == 1) &
                        (dataframe['rsi'] > 50) &
                        (dataframe['close'] < dataframe['bb_upper']),
                        'enter_short'
                    ] = 1
        
        # Fallback: Basic SFP-like signal if Matrix Agent unavailable
        dataframe.loc[
            (
                (dataframe['close'] < dataframe['bb_lower']) &
                (dataframe['rsi'] < 35) &
                (dataframe['matrix_approved'] == 0)
            ),
            'enter_long'
        ] = 1
        
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Populate exit signals.
        
        Args:
            dataframe: Dataframe with data
            metadata: Pair metadata
            
        Returns:
            DataFrame with exit signals
        """
        # Default exit signals
        dataframe['exit_long'] = 0
        dataframe['exit_short'] = 0
        
        # Exit on RSI overbought/oversold
        dataframe.loc[
            (dataframe['rsi'] > 70) & (dataframe['close'] > dataframe['bb_upper']),
            'exit_long'
        ] = 1
        
        dataframe.loc[
            (dataframe['rsi'] < 30) & (dataframe['close'] < dataframe['bb_lower']),
            'exit_short'
        ] = 1
        
        # Exit on profit target (managed by minimal_roi)
        
        return dataframe
    
    def custom_stoploss(
        self,
        pair: str,
        trade: Trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        min_stops: float,
        max_stops: float,
        current_stops_price: float,
        **kwargs
    ) -> float:
        """
        Custom stoploss calculation.
        
        Args:
            pair: Trading pair
            trade: Trade object
            current_time: Current time
            current_rate: Current price
            current_profit: Current profit percentage
            min_stops: Minimum stop price
            max_stops: Maximum stop price
            current_stops_price: Current stop price
            
        Returns:
            Stop loss price
        """
        # Use Matrix Agent stop loss if available
        matrix_analysis = self._get_matrix_analysis_for_pair(pair)
        
        if matrix_analysis and 'stop_loss' in matrix_analysis:
            sl_price = matrix_analysis['stop_loss']
            
            # Ensure stop loss is within bounds
            if self.can_short:
                if sl_price > max_stops:
                    return max_stops
                if sl_price < min_stops:
                    return min_stops
            else:
                if sl_price < min_stops:
                    return min_stops
                if sl_price > max_stops:
                    return max_stops
            
            return stoploss_from_absolute(current_rate, sl_price)
        
        # Default stoploss
        return -0.10
    
    def custom_exit(
        self,
        pair: str,
        trade: Trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        **kwargs
    ) -> tuple:
        """
        Custom exit logic.
        
        Args:
            pair: Trading pair
            trade: Trade object
            current_time: Current time
            current_rate: Current price
            current_profit: Current profit percentage
            
        Returns:
            Tuple of (exit_reason, exit_tag)
        """
        # Check Matrix Agent signal
        matrix_analysis = self._get_matrix_analysis_for_pair(pair)
        
        if matrix_analysis and matrix_analysis.get('approved') == False:
            # Matrix Agent rejected - consider exiting
            if current_profit > 0:
                return 'matrix_rejected_profit', 'matrix_rejected_profit'
            elif current_profit < -0.02:
                return 'matrix_rejected_loss', 'matrix_rejected_loss'
        
        # Exit at profit targets
        if current_profit >= 0.03:
            return 'profit_target_3pct', 'profit_target_3pct'
        elif current_profit >= 0.05:
            return 'profit_target_5pct', 'profit_target_5pct'
        
        # Exit on drawdown
        if current_profit <= -0.08:
            return 'stop_loss', 'stop_loss'
        
        return None, None
    
    def adjust_trade_position(
        self,
        trade: Trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        min_stops: float,
        max_stops: float,
        current_stops_price: float,
        **kwargs
    ) -> Optional[float]:
        """
        Adjust trade position based on Matrix Agent signals.
        
        Args:
            trade: Trade object
            current_time: Current time
            current_rate: Current price
            current_profit: Current profit percentage
            min_stops: Minimum stop price
            max_stops: Maximum stop price
            current_stops_price: Current stop price
            
        Returns:
            Position adjustment amount or None
        """
        # Get Matrix Agent analysis
        matrix_analysis = self._get_matrix_analysis_for_pair(trade.pair)
        
        if not matrix_analysis:
            return None
        
        # Check if we should add to position
        if matrix_analysis.get('approved', False):
            if matrix_analysis.get('signal_strength', 0) >= 0.8:
                if current_profit > 0.02:
                    # Add to winning position
                    return trade.amount * 0.5  # Add 50% of current position
        
        # Check if we should reduce position
        if not matrix_analysis.get('approved', True):
            if current_profit > 0:
                # Reduce winning position
                return -trade.amount * 0.5  # Close 50% of position
        
        return None
    
    def _get_matrix_analysis(
        self,
        dataframe: DataFrame,
        pair: str
    ) -> Optional[dict]:
        """
        Get Matrix Agent analysis for a pair.
        
        Args:
            dataframe: OHLCV data
            pair: Trading pair
            
        Returns:
            Analysis result dictionary or None
        """
        cache_key = f"{pair}_analysis"
        current_time = datetime.now()
        
        # Check cache
        if cache_key in self._analysis_cache:
            cached = self._analysis_cache[cache_key]
            if (current_time - cached['timestamp']).seconds < self._cache_ttl:
                return cached['analysis']
        
        # Get fresh analysis
        try:
            # Create signal from Matrix Agent
            signal = self.matrix_agent.analyze_market(pair)
            
            analysis = {
                'approved': signal.decision.value == 'approve',
                'signal_strength': signal.confidence,
                'expected_r': signal.expected_r,
                'sfp_type': signal.sfp_context.pattern_type if signal.sfp_context else None,
                'sfp_detected': signal.sfp_context is not None,
                'entry_price': signal.entry_price,
                'stop_loss': signal.stop_loss,
                'take_profit_1': signal.take_profit_1,
                'take_profit_2': signal.take_profit_2,
                'macro_approved': signal.macro_analysis.is_approved if signal.macro_analysis else False,
                'consensus_level': signal.consensus_analysis.consensus_level if signal.consensus_analysis else 0,
                'rejection_reason': signal.rejection_reason,
                'timestamp': current_time
            }
            
            # Cache result
            self._analysis_cache[cache_key] = {
                'analysis': analysis,
                'timestamp': current_time
            }
            
            return analysis
            
        except Exception as e:
            logger.error(f"Matrix Agent analysis failed for {pair}: {e}")
            return None
    
    def _get_matrix_analysis_for_pair(self, pair: str) -> Optional[dict]:
        """
        Get cached Matrix Agent analysis for a pair.
        
        Args:
            pair: Trading pair
            
        Returns:
            Analysis result or None
        """
        cache_key = f"{pair}_analysis"
        
        if cache_key in self._analysis_cache:
            return self._analysis_cache[cache_key]['analysis']
        
        return None
    
    def calculate_rsi(self, close: pd.Series, period: int = 14) -> pd.Series:
        """Calculate RSI indicator."""
        delta = close.diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        
        avg_gain = gain.rolling(window=period).mean()
        avg_loss = loss.rolling(window=period).mean()
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def calculate_ema(self, close: pd.Series, period: int) -> pd.Series:
        """Calculate EMA indicator."""
        return close.ewm(span=period, adjust=False).mean()
    
    def calculate_bollinger_bands(
        self,
        close: pd.Series,
        window: int = 20,
        num_std: int = 2
    ) -> dict:
        """Calculate Bollinger Bands."""
        middle = close.rolling(window=window).mean()
        std = close.rolling(window=window).std()
        
        return {
            'upper': middle + (std * num_std),
            'middle': middle,
            'lower': middle - (std * num_std)
        }
    
    def calculate_macd(
        self,
        close: pd.Series,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9
    ) -> dict:
        """Calculate MACD indicator."""
        ema_fast = close.ewm(span=fast, adjust=False).mean()
        ema_slow = close.ewm(span=slow, adjust=False).mean()
        
        macd = ema_fast - ema_slow
        signal_line = macd.ewm(span=signal, adjust=False).mean()
        hist = macd - signal_line
        
        return {
            'macd': macd,
            'signal': signal_line,
            'hist': hist
        }
    
    def bot_start(self, **kwargs) -> None:
        """Called when bot starts."""
        logger.info("MatrixAgentStrategy bot starting")
        # Clear cache on restart
        self._analysis_cache.clear()
    
    def bot_loop_end(self, **kwargs) -> None:
        """Called at the end of each bot loop."""
        # Optionally clear old cache entries
        current_time = datetime.now()
        expired_keys = []
        
        for key, value in self._analysis_cache.items():
            if (current_time - value['timestamp']).seconds > self._cache_ttl:
                expired_keys.append(key)
        
        for key in expired_keys:
            del self._analysis_cache[key]
    
    def __repr__(self):
        return "MatrixAgentStrategy"
