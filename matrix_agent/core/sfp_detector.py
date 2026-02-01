"""
SFP Detector - Swing Failure Pattern Detection
===============================================
Core liquidity hunter module that identifies Swing Failure Patterns.

The ONLY allowed entry logic: SFP (Swing Failure Pattern)
- Bullish SFP: Price breaks below key support, fails to sustain, reclaims support
- Bearish SFP: Price breaks above key resistance, fails to sustain, reclaims resistance

Invalid SFP conditions (must reject):
- No close confirmation
- Not at key high/low point
- Occurs in mid-trend

Author: Matrix Agent
Version: 1.0.0
"""

import numpy as np
import pandas as pd
from typing import Optional, List, Tuple, Dict, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging

from .models import (
    SFPContext, 
    TradeSignal, 
    TradeDirection, 
    SignalSource,
    PriceLevel,
    VetoReason
)

logger = logging.getLogger(__name__)


@dataclass
class SwingPoint:
    """Swing point data structure."""
    index: int
    price: float
    timestamp: datetime
    swing_type: str  # 'high' or 'low'
    strength: float  # 0-1, how significant this swing is
    volume: float
    is_key_level: bool = False


class SFPDetector:
    """
    Swing Failure Pattern Detector
    
    Identifies liquidity grabs at key swing points where price fails to sustain
    beyond the swing and reclaims the level - indicating institutional absorption.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize SFP Detector.
        
        Args:
            config: Configuration dictionary with detection parameters
        """
        self.config = config or self._default_config()
        self.swing_period = self.config.get('swing_period', 5)
        self.min_swing_strength = self.config.get('min_swing_strength', 0.5)
        self.lookback_candles = self.config.get('lookback_candles', 100)
        self.confirmation_bars = self.config.get('confirmation_bars', 1)
        self.tolerance_pct = self.config.get('tolerance_pct', 0.001)  # 0.1% tolerance
        
    def _default_config(self) -> Dict[str, Any]:
        """Return default configuration."""
        return {
            'swing_period': 5,           # Period to identify swing highs/lows
            'min_swing_strength': 0.5,   # Minimum swing strength (0-1)
            'lookback_candles': 100,     # Number of candles to analyze
            'confirmation_bars': 1,      # Bars required for confirmation
            'tolerance_pct': 0.001,      # Price tolerance for level testing
            'volume_threshold': 1.5,     # Volume multiplier for significance
            'max_swing_age_days': 7      # Maximum age of swing points
        }
    
    def detect_sfp(
        self, 
        dataframe: pd.DataFrame, 
        pair: str,
        timeframe: str = "5m"
    ) -> Optional[SFPContext]:
        """
        Detect Swing Failure Pattern in dataframe.
        
        Args:
            dataframe: OHLCV dataframe with price data
            pair: Trading pair symbol
            timeframe: Candle timeframe
            
        Returns:
            SFPContext if valid SFP found, None otherwise
        """
        if dataframe is None or len(dataframe) < self.lookback_candles:
            logger.warning(f"Insufficient data for SFP detection: {pair}")
            return None
        
        # Extract relevant columns
        high = dataframe['high'].values
        low = dataframe['low'].values
        close = dataframe['close'].values
        volume = dataframe['volume'].values
        
        timestamps = dataframe.index if hasattr(dataframe, 'index') else range(len(dataframe))
        
        # Find swing points
        swing_highs = self._find_swing_points(high, low, close, 'high', timestamps, volume)
        swing_lows = self._find_swing_points(high, low, close, 'low', timestamps, volume)
        
        # Look for bullish SFP (swing low failure)
        bullish_sfp = self._check_bullish_sfp(
            dataframe, swing_lows, high, low, close, volume
        )
        
        if bullish_sfp:
            return bullish_sfp
        
        # Look for bearish SFP (swing high failure)
        bearish_sfp = self._check_bearish_sfp(
            dataframe, swing_highs, high, low, close, volume
        )
        
        if bearish_sfp:
            return bearish_sfp
        
        return None
    
    def _find_swing_points(
        self,
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
        swing_type: str,
        timestamps: any,
        volume: np.ndarray
    ) -> List[SwingPoint]:
        """
        Find significant swing points in price data.
        
        Args:
            high: High prices
            low: Low prices
            close: Close prices
            swing_type: 'high' or 'low'
            timestamps: Timestamp array
            volume: Volume array
            
        Returns:
            List of SwingPoint objects
        """
        swing_points = []
        period = self.swing_period
        
        if swing_type == 'high':
            for i in range(period, len(high) - period):
                # Check if this is a local maximum
                if high[i] >= max(high[i-period:i+period+1]):
                    # Calculate swing strength based on prominence
                    left_range = high[i] - min(high[max(0,i-period):i])
                    right_range = high[i] - min(high[i+1:min(len(high), i+period+1)])
                    strength = min(left_range, right_range) / (high[i] + 1e-10)
                    strength = min(strength * 10, 1.0)  # Normalize
                    
                    swing_points.append(SwingPoint(
                        index=i,
                        price=high[i],
                        timestamp=self._get_timestamp(timestamps, i),
                        swing_type='high',
                        strength=strength,
                        volume=volume[i],
                        is_key_level=strength >= self.min_swing_strength
                    ))
        else:  # swing_type == 'low'
            for i in range(period, len(low) - period):
                # Check if this is a local minimum
                if low[i] <= min(low[i-period:i+period+1]):
                    # Calculate swing strength
                    left_range = max(low[max(0,i-period):i]) - low[i]
                    right_range = max(low[i+1:min(len(low), i+period+1)]) - low[i]
                    strength = min(left_range, right_range) / (low[i] + 1e-10)
                    strength = min(strength * 10, 1.0)
                    
                    swing_points.append(SwingPoint(
                        index=i,
                        price=low[i],
                        timestamp=self._get_timestamp(timestamps, i),
                        swing_type='low',
                        strength=strength,
                        volume=volume[i],
                        is_key_level=strength >= self.min_swing_strength
                    ))
        
        return swing_points
    
    def _check_bullish_sfp(
        self,
        dataframe: pd.DataFrame,
        swing_lows: List[SwingPoint],
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
        volume: np.ndarray
    ) -> Optional[SFPContext]:
        """
        Check for bullish Swing Failure Pattern.
        
        Bullish SFP:
        1. Price breaks below key prior low (liquidity grab)
        2. Candle low < that low point (clear violation)
        3. Close price recovers above that low point (failure confirmed)
        """
        if not swing_lows:
            return None
        
        # Sort swing lows by strength and recency
        valid_swings = [s for s in swing_lows if s.is_key_level]
        valid_swings.sort(key=lambda x: (x.strength, -x.index), reverse=True)
        
        for swing in valid_swings[-5:]:  # Check last 5 significant swings
            swing_price = swing.price
            swing_idx = swing.index
            
            if swing_idx >= len(low) - self.confirmation_bars - 1:
                continue
            
            # Check for break below swing low
            break_candle_idx = swing_idx + 1
            if break_candle_idx >= len(low):
                continue
            
            # The break candle must close below the swing low
            break_low = low[break_candle_idx]
            break_close = close[break_candle_idx]
            
            # Bullish SFP requires price to break BELOW the swing low
            if break_low >= swing_price * (1 - self.tolerance_pct):
                continue  # No break below
            
            # Price broke below - now check for recovery
            # Need confirmation bars showing price reclaiming the level
            recovery_confirmed = False
            recovery_idx = None
            
            for i in range(break_candle_idx + 1, 
                          min(break_candle_idx + 1 + self.confirmation_bars * 2, len(close))):
                if close[i] > swing_price * (1 + self.tolerance_pct):
                    recovery_confirmed = True
                    recovery_idx = i
                    break
            
            if not recovery_confirmed:
                continue  # Pattern not confirmed
            
            # Calculate stop loss (below the break low with buffer)
            stop_loss = break_low * 0.99  # 1% buffer below break
            
            # Calculate entry price (recovery point)
            entry_price = swing_price
            
            # Calculate take profit levels
            risk = entry_price - stop_loss
            tp1_price = entry_price + risk * 2   # 2R
            tp2_price = entry_price + risk * 3   # 3R
            
            # Calculate risk-reward ratio
            potential_reward = (tp1_price - entry_price) / entry_price
            risk_amount = (entry_price - stop_loss) / entry_price
            rr_ratio = potential_reward / risk_amount if risk_amount > 0 else 0
            
            # Validate it's not mid-trend (check trend context)
            if self._is_mid_trend(dataframe, swing_idx, 'bullish'):
                logger.debug(f"Bullish SFP rejected - mid-trend condition: {swing}")
                continue
            
            # Check volume confirmation
            avg_volume = np.mean(volume[max(0,swing_idx-20):swing_idx])
            break_volume = volume[break_candle_idx]
            if break_volume < avg_volume * 0.5:
                logger.debug(f"Bullish SFP rejected - low volume confirmation: {swing}")
                continue
            
            return SFPContext(
                pattern_type='bullish_sfp',
                entry_price=entry_price,
                stop_loss=stop_loss,
                failure_point=break_low,
                confirmation_price=close[recovery_idx] if recovery_idx else close[break_candle_idx],
                timeframe=dataframe.get('timeframe', '5m') if 'timeframe' in dataframe.columns else '5m',
                is_valid=True,
                liquidity_zone=swing_price,
                risk_reward_ratio=rr_ratio
            )
        
        return None
    
    def _check_bearish_sfp(
        self,
        dataframe: pd.DataFrame,
        swing_highs: List[SwingPoint],
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
        volume: np.ndarray
    ) -> Optional[SFPContext]:
        """
        Check for bearish Swing Failure Pattern.
        
        Bearish SFP:
        1. Price breaks above key prior high (liquidity grab)
        2. Candle high > that high point (clear violation)
        3. Close price drops back below that high point (failure confirmed)
        """
        if not swing_highs:
            return None
        
        # Sort swing highs by strength and recency
        valid_swings = [s for s in swing_highs if s.is_key_level]
        valid_swings.sort(key=lambda x: (x.strength, -x.index), reverse=True)
        
        for swing in valid_swings[-5:]:  # Check last 5 significant swings
            swing_price = swing.price
            swing_idx = swing.index
            
            if swing_idx >= len(high) - self.confirmation_bars - 1:
                continue
            
            # Check for break above swing high
            break_candle_idx = swing_idx + 1
            if break_candle_idx >= len(high):
                continue
            
            # The break candle must close below the swing high
            break_high = high[break_candle_idx]
            break_close = close[break_candle_idx]
            
            # Bearish SFP requires price to break ABOVE the swing high
            if break_high <= swing_price * (1 + self.tolerance_pct):
                continue  # No break above
            
            # Price broke above - now check for rejection
            # Need confirmation bars showing price failing to sustain
            failure_confirmed = False
            failure_idx = None
            
            for i in range(break_candle_idx + 1, 
                          min(break_candle_idx + 1 + self.confirmation_bars * 2, len(close))):
                if close[i] < swing_price * (1 - self.tolerance_pct):
                    failure_confirmed = True
                    failure_idx = i
                    break
            
            if not failure_confirmed:
                continue  # Pattern not confirmed
            
            # Calculate stop loss (above the break high with buffer)
            stop_loss = break_high * 1.01  # 1% buffer above break
            
            # Calculate entry price (rejection point)
            entry_price = swing_price
            
            # Calculate take profit levels
            risk = stop_loss - entry_price
            tp1_price = entry_price - risk * 2   # 2R
            tp2_price = entry_price - risk * 3   # 3R
            
            # Calculate risk-reward ratio
            potential_reward = (entry_price - tp1_price) / entry_price
            risk_amount = (stop_loss - entry_price) / entry_price
            rr_ratio = potential_reward / risk_amount if risk_amount > 0 else 0
            
            # Validate it's not mid-trend
            if self._is_mid_trend(dataframe, swing_idx, 'bearish'):
                logger.debug(f"Bearish SFP rejected - mid-trend condition: {swing}")
                continue
            
            # Check volume confirmation
            avg_volume = np.mean(volume[max(0,swing_idx-20):swing_idx])
            break_volume = volume[break_candle_idx]
            if break_volume < avg_volume * 0.5:
                logger.debug(f"Bearish SFP rejected - low volume confirmation: {swing}")
                continue
            
            return SFPContext(
                pattern_type='bearish_sfp',
                entry_price=entry_price,
                stop_loss=stop_loss,
                failure_point=break_high,
                confirmation_price=close[failure_idx] if failure_idx else close[break_candle_idx],
                timeframe=dataframe.get('timeframe', '5m') if 'timeframe' in dataframe.columns else '5m',
                is_valid=True,
                liquidity_zone=swing_price,
                risk_reward_ratio=rr_ratio
            )
        
        return None
    
    def _is_mid_trend(self, dataframe: pd.DataFrame, swing_idx: int, 
                     direction: str) -> bool:
        """
        Check if SFP occurs in mid-trend (invalid) vs trend reversal (valid).
        
        Args:
            dataframe: Price data
            swing_idx: Swing point index
            direction: 'bullish' or 'bearish'
            
        Returns:
            True if mid-trend (should reject), False if reversal context
        """
        if swing_idx < 50:
            return True  # Not enough data to determine trend
        
        # Look at prior price action to determine trend context
        lookback = min(50, swing_idx)
        
        if direction == 'bullish':
            # For bullish SFP, check if we're in downtrend or range
            recent_highs = dataframe['high'].values[swing_idx-lookback:swing_idx]
            recent_lows = dataframe['low'].values[swing_idx-lookback:swing_idx]
            
            # Check if price is making lower highs and lower lows (downtrend)
            lower_highs = all(recent_highs[i] >= recent_highs[i+1] 
                            for i in range(len(recent_highs)-1))
            lower_lows = all(recent_lows[i] >= recent_lows[i+1] 
                           for i in range(len(recent_lows)-1))
            
            if lower_highs and lower_lows:
                return False  # Downtrend context - bullish SFP is valid reversal
            
            # Check if we're in range (neither clearly up nor down)
            price_range = max(recent_highs) - min(recent_lows)
            current_position = (dataframe['close'].values[swing_idx] - min(recent_lows)) / price_range
            
            if 0.3 < current_position < 0.7:
                return True  # Mid-range - higher risk, might reject
            
            return False
        
        else:  # bearish
            # For bearish SFP, check if we're in uptrend
            recent_highs = dataframe['high'].values[swing_idx-lookback:swing_idx]
            recent_lows = dataframe['low'].values[swing_idx-lookback:swing_idx]
            
            # Check if price is making higher highs and higher lows (uptrend)
            higher_highs = all(recent_highs[i] <= recent_highs[i+1] 
                             for i in range(len(recent_highs)-1))
            higher_lows = all(recent_lows[i] <= recent_lows[i+1] 
                            for i in range(len(recent_lows)-1))
            
            if higher_highs and higher_lows:
                return False  # Uptrend context - bearish SFP is valid reversal
            
            # Check if we're in range
            price_range = max(recent_highs) - min(recent_lows)
            current_position = (dataframe['close'].values[swing_idx] - min(recent_lows)) / price_range
            
            if 0.3 < current_position < 0.7:
                return True  # Mid-range
            
            return False
    
    def _get_timestamp(self, timestamps: any, index: int) -> datetime:
        """Get timestamp for a given index."""
        if hasattr(timestamps, '__getitem__'):
            if hasattr(timestamps[index], 'timestamp'):
                return timestamps[index].timestamp()
            elif isinstance(timestamps[index], (int, float)):
                return datetime.fromtimestamp(timestamps[index])
            else:
                return timestamps[index]
        return datetime.now()
    
    def find_key_levels(self, dataframe: pd.DataFrame, 
                       num_levels: int = 5) -> List[PriceLevel]:
        """
        Find significant key levels (support/resistance) in price data.
        
        Args:
            dataframe: OHLCV price data
            num_levels: Number of key levels to identify
            
        Returns:
            List of PriceLevel objects
        """
        high = dataframe['high'].values
        low = dataframe['low'].values
        close = dataframe['close'].values
        volume = dataframe['volume'].values
        
        # Use volume profile to find significant levels
        price_range = high.max() - low.min()
        num_bins = min(50, len(dataframe) // 4)
        bin_size = price_range / num_bins
        
        # Create volume profile
        volume_profile = np.zeros(num_bins)
        
        for i in range(len(dataframe)):
            price = (high[i] + low[i] + close[i]) / 3  # Typical price
            bin_idx = min(int((price - low.min()) / bin_size), num_bins - 1)
            volume_profile[bin_idx] += volume[i]
        
        # Find high volume nodes (significant levels)
        volume_threshold = np.mean(volume_profile) + np.std(volume_profile)
        level_bins = np.where(volume_profile > volume_threshold)[0]
        
        # Sort by volume to get most significant levels
        level_bins = sorted(level_bins, key=lambda x: volume_profile[x], reverse=True)
        
        key_levels = []
        for bin_idx in level_bins[:num_levels]:
            price_level = low.min() + bin_idx * bin_size
            
            # Determine if support or resistance
            current_price = close[-1]
            level_type = 'support' if price_level < current_price else 'resistance'
            
            key_levels.append(PriceLevel(
                price=price_level,
                timestamp=datetime.now(),
                volume=volume_profile[bin_idx],
                is_key_level=True,
                level_type=level_type
            ))
        
        return key_levels
    
    def validate_sfp(self, sfp: SFPContext) -> Tuple[bool, str]:
        """
        Validate a detected SFP pattern.
        
        Args:
            sfp: SFPContext to validate
            
        Returns:
            Tuple of (is_valid, reason)
        """
        # Check for close confirmation
        if not sfp.confirmation_price:
            return False, "No close confirmation"
        
        # Check if at key level
        if not sfp.liquidity_zone:
            return False, "Not at key high/low point"
        
        # Check pattern type
        if sfp.pattern_type not in ['bullish_sfp', 'bearish_sfp']:
            return False, "Invalid pattern type"
        
        # Check risk-reward ratio
        if sfp.risk_reward_ratio < 2.0:
            return False, f"Risk-reward ratio too low: {sfp.risk_reward_ratio:.2f}"
        
        # Validate price relationships
        if sfp.pattern_type == 'bullish_sfp':
            if sfp.entry_price <= sfp.stop_loss:
                return False, "Invalid bullish SFP: entry must be above stop loss"
            if sfp.confirmation_price <= sfp.entry_price:
                return False, "Invalid bullish SFP: confirmation must be above entry"
                
        else:  # bearish_sfp
            if sfp.entry_price >= sfp.stop_loss:
                return False, "Invalid bearish SFP: entry must be below stop loss"
            if sfp.confirmation_price >= sfp.entry_price:
                return False, "Invalid bearish SFP: confirmation must be below entry"
        
        return True, "Valid SFP"
