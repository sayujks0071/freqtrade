"""
Macro Gatekeeper - Veto Layer Analysis
=======================================
Layer 1 of the Matrix Agent system.

Determines if a trade is worth being swept based on macro conditions:
- Trend (UP / DOWN / RANGE)
- RSI (4H / 1D)
- Funding Rate
- Price position (edge / middle)

APPROVED Conditions:
- Clear trend + RSI pullback zone (40-45 / 55-60)
- Extreme Funding (≤ -0.03% or ≥ +0.05%)
- Price at high/low/liquidity edge

REJECTED Conditions:
- RSI ≈ 50
- Price in range middle
- Mild positive Funding with rising trend

Author: Matrix Agent
Version: 1.0.0
"""

import numpy as np
import pandas as pd
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging

from .models import (
    MacroAnalysis, 
    MarketState, 
    TrendDirection, 
    PriceLevel,
    VetoReason
)

logger = logging.getLogger(__name__)


class MacroGatekeeper:
    """
    Macro Market Gatekeeper
    
    Veto layer that evaluates whether a trading setup is worth pursuing
    based on macro timeframe analysis (4H and 1D).
    
    Key Philosophy:
    - "Is this worth being swept?" - not "What direction?"
    - Conservative approval criteria
    - Rejection is a successful outcome
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize Macro Gatekeeper.
        
        Args:
            config: Configuration dictionary with thresholds
        """
        self.config = config or self._default_config()
        
        # RSI thresholds
        self.rsi_bullish_low = self.config.get('rsi_bullish_low', 40)
        self.rsi_bullish_high = self.config.get('rsi_bullish_high', 45)
        self.rsi_bearish_low = self.config.get('rsi_bearish_low', 55)
        self.rsi_bearish_high = self.config.get('rsi_bearish_high', 60)
        self.rsi_middle_zone = self.config.get('rsi_middle_zone', 48)  # ±2 from 50
        
        # Funding thresholds
        self.extreme_funding_short = self.config.get('extreme_funding_short', -0.0003)  # -0.03%
        self.extreme_funding_long = self.config.get('extreme_funding_long', 0.0005)    # +0.05%
        
        # Trend detection
        self.adx_threshold = self.config.get('adx_threshold', 25)  # ADX > 25 = trending
        self.ema_fast = self.config.get('ema_fast', 9)
        self.ema_medium = self.config.get('ema_medium', 21)
        self.ema_slow = self.config.get('ema_slow', 50)
        
    def _default_config(self) -> Dict[str, Any]:
        """Return default configuration."""
        return {
            'rsi_bullish_low': 40,
            'rsi_bullish_high': 45,
            'rsi_bearish_low': 55,
            'rsi_bearish_high': 60,
            'rsi_middle_zone': 48,
            'extreme_funding_short': -0.0003,
            'extreme_funding_long': 0.0005,
            'adx_threshold': 25,
            'ema_fast': 9,
            'ema_medium': 21,
            'ema_slow': 50,
            'require_4h_confirmation': True,
            'require_1d_confirmation': False,
            'min_trend_strength': 0.02  # 2% price movement
        }
    
    def analyze(
        self, 
        market_state: MarketState,
        dataframe_4h: Optional[pd.DataFrame] = None,
        dataframe_1d: Optional[pd.DataFrame] = None
    ) -> MacroAnalysis:
        """
        Perform macro analysis and return approval/rejection.
        
        Args:
            market_state: Current market state snapshot
            dataframe_4h: 4-hour timeframe data (optional)
            dataframe_1d: 1-day timeframe data (optional)
            
        Returns:
            MacroAnalysis with approval/rejection decision
        """
        analysis = MacroAnalysis()
        
        # Extract market data
        rsi_4h = market_state.rsi_4h
        rsi_1d = market_state.rsi_1d
        funding = market_state.funding_rate
        trend_4h = market_state.trend_4h
        trend_1d = market_state.trend_1d
        price = market_state.current_price
        key_levels = market_state.key_levels
        
        # Set RSI values
        analysis.rsi_4h = rsi_4h
        analysis.rsi_1d = rsi_1d
        
        # Determine trend (if not provided)
        if trend_4h == TrendDirection.UNKNOWN and dataframe_4h is not None:
            trend_4h = self._detect_trend(dataframe_4h)
        
        if trend_1d == TrendDirection.UNKNOWN and dataframe_1d is not None:
            trend_1d = self._detect_trend(dataframe_1d)
        
        # Use 4H trend as primary
        analysis.trend = trend_4h
        
        # Determine price position
        price_position = self._get_price_position(price, key_levels)
        analysis.price_position = price_position
        
        # Evaluate approval conditions
        approved, approval_reason = self._evaluate_approval(
            rsi_4h, rsi_1d, funding, trend_4h, trend_1d, price_position
        )
        
        analysis.is_approved = approved
        analysis.approval_condition = approval_reason
        
        if not approved:
            rejection_reason = self._get_rejection_reason(
                rsi_4h, rsi_1d, funding, trend_4h, trend_1d, price_position
            )
            analysis.rejection_reason = rejection_reason
            analysis.market_sentiment = self._get_sentiment(
                rsi_4h, rsi_1d, funding, trend_4h, trend_1d
            )
        
        # Store key levels
        analysis.key_levels = key_levels
        
        return analysis
    
    def _detect_trend(self, dataframe: pd.DataFrame) -> TrendDirection:
        """
        Detect trend direction from price data.
        
        Uses multiple indicators:
        - Price relative to EMAs
        - ADX indicator
        - Higher highs / higher lows pattern
        
        Args:
            dataframe: OHLCV price data
            
        Returns:
            TrendDirection enum value
        """
        if dataframe is None or len(dataframe) < 100:
            return TrendDirection.UNKNOWN
        
        close = dataframe['close'].values
        
        # Calculate EMAs
        ema_fast = self._calculate_ema(close, self.ema_fast)
        ema_medium = self._calculate_ema(close, self.ema_medium)
        ema_slow = self._calculate_ema(close, self.ema_slow)
        
        current_close = close[-1]
        current_ema_fast = ema_fast[-1] if len(ema_fast) > 0 else current_close
        current_ema_medium = ema_medium[-1] if len(ema_medium) > 0 else current_close
        current_ema_slow = ema_slow[-1] if len(ema_slow) > 0 else current_close
        
        # Check ADX if available
        adx_value = 0
        if 'adx' in dataframe.columns:
            adx_value = dataframe['adx'].values[-1]
        
        # Determine trend based on EMA relationships
        above_slow = current_close > current_ema_slow
        above_medium = current_close > current_ema_medium
        above_fast = current_close > current_ema_fast
        medium_above_slow = current_ema_medium > current_ema_slow
        fast_above_medium = current_ema_fast > current_ema_medium
        
        # Strong uptrend
        if all([above_slow, above_medium, above_fast, medium_above_slow, fast_above_medium]):
            if adx_value >= self.adx_threshold:
                return TrendDirection.UP
        
        # Strong downtrend
        below_slow = current_close < current_ema_slow
        below_medium = current_close < current_ema_medium
        below_fast = current_close < current_ema_fast
        medium_below_slow = current_ema_medium < current_ema_slow
        fast_below_medium = current_ema_fast < current_ema_medium
        
        if all([below_slow, below_medium, below_fast, medium_below_slow, fast_below_medium]):
            if adx_value >= self.adx_threshold:
                return TrendDirection.DOWN
        
        # Check for range-bound market
        price_range = max(close[-50:]) - min(close[-50:])
        avg_price = np.mean(close[-50:])
        range_pct = price_range / avg_price if avg_price > 0 else 0
        
        if range_pct < 0.03:  # Less than 3% range = likely range-bound
            return TrendDirection.RANGE
        
        # Default to range if uncertain
        return TrendDirection.RANGE
    
    def _calculate_ema(self, data: np.ndarray, period: int) -> np.ndarray:
        """Calculate Exponential Moving Average."""
        if len(data) < period:
            return np.array(data)
        
        ema = np.zeros(len(data))
        ema[:period] = data[:period]
        
        multiplier = 2 / (period + 1)
        
        for i in range(period, len(data)):
            ema[i] = (data[i] - ema[i-1]) * multiplier + ema[i-1]
        
        return ema
    
    def _get_price_position(self, price: float, 
                           key_levels: List[PriceLevel]) -> str:
        """
        Determine price position relative to key levels.
        
        Returns:
            'edge' if at high/low/liquidity edge, 'middle' otherwise
        """
        if not key_levels:
            # Calculate position based on recent range
            return "middle"
        
        # Find closest support and resistance
        supports = [l for l in key_levels if l.level_type == 'support']
        resistances = [l for l in key_levels if l.level_type == 'resistance']
        
        if not supports and not resistances:
            return "middle"
        
        # Calculate position in range
        lowest_support = min([l.price for l in supports]) if supports else price * 0.95
        highest_resistance = max([l.price for l in resistances]) if resistances else price * 1.05
        
        range_size = highest_resistance - lowest_support
        if range_size <= 0:
            return "middle"
        
        position_from_bottom = (price - lowest_support) / range_size
        
        # At edges if within 10% of support or resistance
        if position_from_bottom < 0.10:
            return "edge"  # Near support
        elif position_from_bottom > 0.90:
            return "edge"  # Near resistance
        else:
            return "middle"
    
    def _evaluate_approval(
        self,
        rsi_4h: float,
        rsi_1d: float,
        funding: float,
        trend: TrendDirection,
        trend_1d: TrendDirection,
        price_position: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Evaluate if trade meets approval conditions.
        
        APPROVED Conditions (any one triggers approval):
        1. Clear trend + RSI pullback zone (40-45 / 55-60)
        2. Extreme Funding (≤ -0.03% or ≥ +0.05%)
        3. Price at high/low/liquidity edge
        
        Returns:
            Tuple of (is_approved, reason)
        """
        # Condition 1: Clear trend + RSI pullback
        if trend == TrendDirection.UP:
            # RSI pullback in bullish zone (40-45)
            if self.rsi_bullish_low <= rsi_4h <= self.rsi_bullish_high:
                return True, f"Uptrend with RSI pullback (RSI: {rsi_4h:.1f})"
        
        if trend == TrendDirection.DOWN:
            # RSI pullback in bearish zone (55-60)
            if self.rsi_bearish_low <= rsi_4h <= self.rsi_bearish_high:
                return True, f"Downtrend with RSI overbought pullback (RSI: {rsi_4h:.1f})"
        
        # Condition 2: Extreme funding
        if funding <= self.extreme_funding_short:
            return True, f"Extreme short funding ({funding*100:.2f}%)"
        
        if funding >= self.extreme_funding_long:
            return True, f"Extreme long funding ({funding*100:.2f}%)"
        
        # Condition 3: Price at edge
        if price_position == "edge":
            return True, f"Price at liquidity edge"
        
        # Check 1D confirmation for additional confidence
        if trend_1d == TrendDirection.UP and self.rsi_bullish_low <= rsi_1d <= self.rsi_bullish_high:
            return True, f"Daily timeframe confirming uptrend with RSI pullback"
        
        if trend_1d == TrendDirection.DOWN and self.rsi_bearish_low <= rsi_1d <= self.rsi_bearish_high:
            return True, f"Daily timeframe confirming downtrend with RSI pullback"
        
        return False, None
    
    def _get_rejection_reason(
        self,
        rsi_4h: float,
        rsi_1d: float,
        funding: float,
        trend: TrendDirection,
        trend_1d: TrendDirection,
        price_position: str
    ) -> Optional[str]:
        """
        Determine specific rejection reason.
        
        REJECTED Conditions:
        - RSI ≈ 50
        - Price in range middle
        - Mild positive Funding with rising trend
        """
        # RSI in middle zone
        rsi_middle_threshold = 2  # ±2 from 50
        if abs(rsi_4h - 50) < rsi_middle_threshold:
            return f"RSI in neutral zone ({rsi_4h:.1f})"
        
        # Price in middle of range
        if price_position == "middle":
            return "Price in middle of range (no clear edge)"
        
        # Mild funding with trending market
        if (trend == TrendDirection.UP or trend == TrendDirection.DOWN):
            if 0 < funding < self.extreme_funding_long:
                if trend == TrendDirection.UP and funding > 0:
return f"Mild long funding ({funding*100:.2f}%) in uptrend (consensus risk)"
                if trend == TrendDirection.DOWN and funding < 0:
                    return f"Mild short funding ({funding*100:.2f}%) in downtrend (consensus risk)"
        
        # No approval condition met
        return "No approval condition met"
    
    def _get_sentiment(
        self,
        rsi_4h: float,
        rsi_1d: float,
        funding: float,
        trend: TrendDirection,
        trend_1d: TrendDirection
    ) -> str:
        """Determine market sentiment from indicators."""
        # Calculate composite sentiment
        rsi_score = (rsi_4h - 50) / 50  # -1 to 1
        funding_score = funding * 1000  # Scale funding
        
        composite = rsi_score + funding_score
        
        if composite > 0.3:
            return "bullish"
        elif composite < -0.3:
            return "bearish"
        else:
            return "neutral"
    
    def analyze_with_data(
        self,
        dataframe: pd.DataFrame,
        funding_rate: float = 0.0,
        timeframe: str = "4h"
    ) -> MacroAnalysis:
        """
        Perform complete macro analysis from raw dataframe.
        
        Args:
            dataframe: OHLCV price data
            funding_rate: Current funding rate
            timeframe: Timeframe of data
            
        Returns:
            MacroAnalysis with approval/rejection
        """
        # Calculate RSI
        close = dataframe['close'].values
        rsi = self._calculate_rsi(close, period=14)
        current_rsi = rsi[-1] if len(rsi) > 0 else 50.0
        
        # Detect trend
        trend = self._detect_trend(dataframe)
        
        # Find key levels
        key_levels = self._find_key_levels(dataframe)
        
        # Build market state
        market_state = MarketState(
            pair="",
            current_price=close[-1],
            timestamp=datetime.now(),
            trend_4h=trend if timeframe == "4h" else TrendDirection.UNKNOWN,
            trend_1d=trend if timeframe == "1d" else TrendDirection.UNKNOWN,
            rsi_4h=current_rsi if timeframe == "4h" else 50.0,
            rsi_1d=current_rsi if timeframe == "1d" else 50.0,
            funding_rate=funding_rate,
            key_levels=key_levels
        )
        
        # Perform analysis
        return self.analyze(market_state, dataframe_4h=dataframe if timeframe == "4h" else None)
    
    def _calculate_rsi(self, data: np.ndarray, period: int = 14) -> np.ndarray:
        """Calculate RSI indicator."""
        if len(data) < period + 1:
            return np.array([50.0] * len(data))
        
        delta = np.diff(data)
        gain = np.where(delta > 0, delta, 0)
        loss = np.where(delta < 0, -delta, 0)
        
        avg_gain = np.mean(gain[:period])
        avg_loss = np.mean(loss[:period])
        
        rsi = np.zeros(len(data))
        rsi[:period] = 50
        
        for i in range(period, len(data)):
            avg_gain = (avg_gain * (period - 1) + gain[i]) / period
            avg_loss = (avg_loss * (period - 1) + loss[i]) / period
            
            if avg_loss == 0:
                rsi[i] = 100
            else:
                rs = avg_gain / avg_loss
                rsi[i] = 100 - (100 / (1 + rs))
        
        return rsi
    
    def _find_key_levels(self, dataframe: pd.DataFrame) -> List[PriceLevel]:
        """Find significant key levels from price data."""
        high = dataframe['high'].values
        low = dataframe['low'].values
        close = dataframe['close'].values
        
        levels = []
        
        # Find recent highs and lows
        lookback = min(50, len(dataframe))
        
        for i in range(lookback, len(dataframe)):
            is_high = all(high[i] >= high[max(0, i-5):min(len(high), i+6)])
            is_low = all(low[i] <= low[max(0, i-5):min(len(low), i+6)])
            
            if is_high:
                levels.append(PriceLevel(
                    price=high[i],
                    timestamp=datetime.now(),
                    volume=dataframe['volume'].values[i] if 'volume' in dataframe.columns else 0,
                    is_key_level=True,
                    level_type='resistance'
                ))
            elif is_low:
                levels.append(PriceLevel(
                    price=low[i],
                    timestamp=datetime.now(),
                    volume=dataframe['volume'].values[i] if 'volume' in dataframe.columns else 0,
                    is_key_level=True,
                    level_type='support'
                ))
        
        # Sort by price and return unique levels
        levels.sort(key=lambda x: x.price)
        
        # Remove levels that are too close
        filtered_levels = []
        min_distance = (max(high) - min(low)) * 0.02  # 2% minimum distance
        
        for level in levels:
            if not filtered_levels:
                filtered_levels.append(level)
            else:
                last = filtered_levels[-1]
                if abs(level.price - last.price) > last.price * min_distance:
                    filtered_levels.append(level)
        
        return filtered_levels[:10]  # Return top 10 levels
