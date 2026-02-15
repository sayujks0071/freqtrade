"""
Anti-Consensus Filter - Market Sentiment Analysis
==================================================
Layer 2 of the Matrix Agent system.

Analyzes market consensus to avoid trading with the crowd:
- High consensus → Raise Expected R threshold to ≥ 4
- Prohibit chasing price
- Only allow SFP reversal

Consensus Signals:
- High Funding
- Rapidly rising OI
- Extreme sentiment
- Just broke obvious high/low

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
    ConsensusAnalysis,
    MarketState,
    VetoReason
)

logger = logging.getLogger(__name__)


class AntiConsensusFilter:
    """
    Anti-Consensus Market Filter

    Evaluates market sentiment and consensus levels to avoid:
    - Trading in the same direction as the crowd
    - Chasing price after breakouts
    - Entering at obvious levels where everyone is positioned

    Philosophy:
    "The more consensus in the market, the more cautious you become."
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize Anti-Consensus Filter.

        Args:
            config: Configuration dictionary with thresholds
        """
        self.config = config or self._default_config()

        # Consensus thresholds (0-100 scale)
        self.high_consensus_threshold = self.config.get('high_consensus_threshold', 70)
        self.extreme_consensus_threshold = self.config.get('extreme_consensus_threshold', 90)

        # Funding thresholds
        self.high_funding = self.config.get('high_funding', 0.0002)  # +0.02%
        self.extreme_funding = self.config.get('extreme_funding', 0.0005)  # +0.05%
        self.low_funding = self.config.get('low_funding', -0.0002)  # -0.02%
        self.extreme_low_funding = self.config.get('extreme_low_funding', -0.0005)  # -0.05%

        # OI thresholds
        self.oi_rising_fast = self.config.get('oi_rising_fast', 0.05)  # 5% daily increase
        self.oi_falling_fast = self.config.get('oi_falling_fast', -0.05)

        # Sentiment thresholds
        self.extreme_greed = self.config.get('extreme_greed', 80)
        self.extreme_fear = self.config.get('extreme_fear', 20)

        # Required Expected R thresholds
        self.base_required_rr = self.config.get('base_required_rr', 3.0)
        self.high_consensus_rr = self.config.get('high_consensus_rr', 4.0)
        self.extreme_consensus_rr = self.config.get('extreme_consensus_rr', 6.0)

    def _default_config(self) -> Dict[str, Any]:
        """Return default configuration."""
        return {
            'high_consensus_threshold': 70,
            'extreme_consensus_threshold': 90,
            'high_funding': 0.0002,
            'extreme_funding': 0.0005,
            'low_funding': -0.0002,
            'extreme_low_funding': -0.0005,
            'oi_rising_fast': 0.05,
            'oi_falling_fast': -0.05,
            'extreme_greed': 80,
            'extreme_fear': 20,
            'base_required_rr': 3.0,
            'high_consensus_rr': 4.0,
            'extreme_consensus_rr': 6.0,
            'allow_chasing': False,
            'require_sfp_reversal': True
        }

    def analyze(
        self,
        market_state: MarketState,
        funding_history: Optional[List[float]] = None,
        oi_history: Optional[List[float]] = None,
        sentiment_data: Optional[Dict[str, Any]] = None
    ) -> ConsensusAnalysis:
        """
        Perform consensus analysis and return recommendations.

        Args:
            market_state: Current market state
            funding_history: Recent funding rate history
            oi_history: Recent open interest history
            sentiment_data: Sentiment data from external sources

        Returns:
            ConsensusAnalysis with consensus level and recommendations
        """
        analysis = ConsensusAnalysis()

        # Calculate individual consensus indicators
        funding_indicator = self._analyze_funding(market_state.funding_rate, funding_history)
        oi_indicator = self._analyze_oi(market_state.open_interest, oi_history)
        sentiment_indicator = self._analyze_sentiment(sentiment_data)

        # Combine indicators into overall consensus score (0-100)
        consensus_score = self._calculate_consensus_score(
            funding_indicator,
            oi_indicator,
            sentiment_indicator
        )

        analysis.consensus_level = consensus_score
        analysis.funding_indicator = funding_indicator
        analysis.oi_indicator = oi_indicator
        analysis.sentiment_indicator = sentiment_indicator

        # Determine if consensus is too high
        if consensus_score >= self.extreme_consensus_threshold:
            analysis.is_high_consensus = True
            analysis.required_expected_r = self.extreme_consensus_rr
            analysis.warning_reason = "Extreme consensus detected - extremely cautious approach required"
            analysis.can_trade = False  # Extreme consensus = no trade
        elif consensus_score >= self.high_consensus_threshold:
            analysis.is_high_consensus = True
            analysis.required_expected_r = self.high_consensus_rr
            analysis.warning_reason = "High consensus - require higher ExpectedR"
            analysis.can_trade = True  # But with higher bar
        else:
            analysis.is_high_consensus = False
            analysis.required_expected_r = self.base_required_rr
            analysis.can_trade = True

        return analysis

    def _analyze_funding(
        self,
        current_funding: float,
        history: Optional[List[float]] = None
    ) -> float:
        """
        Analyze funding rate to determine consensus.

        Returns:
            Indicator value (-100 to 100):
            - Positive = Long consensus (greed)
            - Negative = Short consensus (fear)
            - Magnitude = strength of consensus
        """
        if current_funding is None:
            return 0.0

        # Base indicator from current funding
        funding_pct = current_funding * 100  # Convert to percentage

        if current_funding >= self.extreme_funding:
            return 100  # Extreme long consensus
        elif current_funding >= self.high_funding:
            return 75   # Strong long consensus
        elif current_funding > 0:
            return current_funding / self.high_funding * 50  # Moderate long consensus
        elif current_funding <= self.extreme_low_funding:
            return -100  # Extreme short consensus
        elif current_funding <= self.low_funding:
            return -75   # Strong short consensus
        else:
            return current_funding / abs(self.low_funding) * -50  # Moderate short consensus

    def _analyze_oi(
        self,
        current_oi: float,
        history: Optional[List[float]] = None
    ) -> float:
        """
        Analyze open interest to determine consensus.

        Rising OI in trending market = consensus building
        Falling OI = consensus fading

        Returns:
            Indicator value (-100 to 100)
        """
        if current_oi is None or current_oi == 0:
            return 0.0

        if history is None or len(history) < 2:
            return 0.0

        # Calculate OI change rate
        oi_change = (current_oi - history[0]) / history[0] if history[0] > 0 else 0

        # Normalize to indicator scale
        if oi_change >= self.oi_rising_fast:
            return 100  # Rapid OI rise = strong consensus
        elif oi_change >= self.oi_rising_fast * 0.5:
            return 75   # Moderate OI rise
        elif oi_change >= 0:
            return oi_change / self.oi_rising_fast * 50  # Slight OI rise
        elif oi_change <= self.oi_falling_fast:
            return -100  # Rapid OI fall = strong short consensus
        elif oi_change <= self.oi_falling_fast * 0.5:
            return -75   # Moderate OI fall
        else:
            return oi_change / abs(self.oi_falling_fast) * -50  # Slight OI fall

    def _analyze_sentiment(
        self,
        sentiment_data: Optional[Dict[str, Any]] = None
    ) -> float:
        """
        Analyze external sentiment data.

        Args:
            sentiment_data: Dict with 'value' (0-100) and optionally 'source'

        Returns:
            Indicator value (-100 to 100)
        """
        if sentiment_data is None:
            return 0.0

        sentiment_value = sentiment_data.get('value', 50)

        # Convert 0-100 scale to -100 to 100
        return (sentiment_value - 50) * 2

    def _calculate_consensus_score(
        self,
        funding_indicator: float,
        oi_indicator: float,
        sentiment_indicator: float
    ) -> float:
        """
        Calculate overall consensus score from individual indicators.

        Uses weighted average with funding as primary signal.

        Returns:
            Consensus score (0-100)
        """
        # Weight the indicators
        weights = {
            'funding': 0.5,
            'oi': 0.3,
            'sentiment': 0.2
        }

        # Normalize indicators to same scale
        funding_norm = abs(funding_indicator) / 100  # 0-1
        oi_norm = abs(oi_indicator) / 100  # 0-1
        sentiment_norm = abs(sentiment_indicator) / 100  # 0-1

        # Calculate weighted score
        consensus_score = (
            funding_norm * weights['funding'] +
            oi_norm * weights['oi'] +
            sentiment_norm * weights['sentiment']
        ) * 100

        # Adjust for direction - consensus is strongest when
        # indicators agree on direction
        direction_alignment = 1.0

        # Check if indicators agree on direction
        indicators = [funding_indicator, oi_indicator, sentiment_indicator]
        positive_count = sum(1 for i in indicators if i > 10)
        negative_count = sum(1 for i in indicators if i < -10)

        if positive_count >= 2:
            direction_alignment = 1.2  # Strong agreement
        elif negative_count >= 2:
            direction_alignment = 1.2  # Strong agreement
        elif positive_count == 1 and negative_count == 1:
            direction_alignment = 0.7  # Mixed signals

        final_score = min(consensus_score * direction_alignment, 100)

        return final_score

    def check_chasing_risk(
        self,
        price: float,
        breakout_level: float,
        direction: str,
        time_since_breakout_minutes: float
    ) -> Tuple[bool, str]:
        """
        Check if entry would be chasing price after breakout.

        Args:
            price: Current price
            breakout_level: Level that was just broken
            direction: 'long' or 'short'
            time_since_breakout_minutes: Time since breakout

        Returns:
            Tuple of (is_chasing, reason)
        """
        # Calculate how far price has moved from breakout
        if direction == 'long':
            move_pct = (price - breakout_level) / breakout_level * 100
        else:
            move_pct = (breakout_level - price) / breakout_level * 100

        # Chasing thresholds
        chasing_threshold = 1.0  # 1% move after breakout
        max_time_before_chasing = 30  # minutes

        if move_pct > chasing_threshold * 2:
            return True, f"Price moved {move_pct:.2f}% past breakout level"

        if time_since_breakout_minutes > max_time_before_chasing and move_pct > chasing_threshold * 0.5:
            return True, f"Breakout stale ({time_since_breakout_minutes:.0f}min), price moved {move_pct:.2f}%"

        if move_pct > chasing_threshold and time_since_breakout_minutes > 15:
            return True, f"Chasing with {move_pct:.2f}% move, {time_since_breakout_minutes:.0f}min old"

        return False, "Not chasing"

    def require_sfp_reversal_confirmation(
        self,
        consensus_level: float,
        has_sfp: bool
    ) -> Tuple[bool, str]:
        """
        Determine if SFP reversal confirmation is required.

        At high consensus, only SFP reversals are allowed.

        Args:
            consensus_level: Current consensus level (0-100)
            has_sfp: Whether SFP pattern is detected

        Returns:
            Tuple of (requires_confirmation, reason)
        """
        if consensus_level >= self.high_consensus_threshold:
            if not has_sfp:
                return True, "High consensus requires SFP reversal"
            else:
                return True, "SFP confirmed - entry allowed"

        if consensus_level >= self.extreme_consensus_threshold:
            if not has_sfp:
                return True, "Extreme consensus - only SFP entries allowed"
            else:
                return True, "Extreme consensus - SFP reversal required"

        return False, "No SFP requirement at this consensus level"

    def get_consensus_warning(self, analysis: ConsensusAnalysis) -> str:
        """
        Generate warning message based on consensus analysis.

        Args:
            analysis: ConsensusAnalysis result

        Returns:
            Warning string or empty string if no warning
        """
        warnings = []

        if analysis.funding_indicator > 75:
            warnings.append(f"High long funding ({analysis.funding_indicator:.0f}%)")
        elif analysis.funding_indicator < -75:
            warnings.append(f"High short funding ({abs(analysis.funding_indicator):.0f}%)")

        if analysis.oi_indicator > 75:
            warnings.append(f"Rapid OI increase ({analysis.oi_indicator:.0f}%)")
        elif analysis.oi_indicator < -75:
            warnings.append(f"Rapid OI decrease ({abs(analysis.oi_indicator):.0f}%)")

        if analysis.sentiment_indicator > 50:
            warnings.append("Extreme greed sentiment")
        elif analysis.sentiment_indicator < -50:
            warnings.append("Extreme fear sentiment")

        if analysis.is_high_consensus:
            warnings.append(f"Required Expected R: {analysis.required_expected_r:.1f}")

        return " | ".join(warnings) if warnings else ""

    def adjust_for_consensus(self, expected_r: float,
                            consensus_level: float) -> float:
        """
        Adjust expected R requirement based on consensus.

        Args:
            expected_r: Original expected R
            consensus_level: Current consensus level (0-100)

        Returns:
            Adjusted expected R threshold
        """
        if consensus_level >= self.extreme_consensus_threshold:
            return max(expected_r, self.extreme_consensus_rr)
        elif consensus_level >= self.high_consensus_threshold:
            return max(expected_r, self.high_consensus_rr)
        else:
            return expected_r

    def should_reject_trade(
        self,
        analysis: ConsensusAnalysis,
        has_sfp: bool,
        is_chasing: bool
    ) -> Tuple[bool, str]:
        """
        Determine if trade should be rejected based on consensus.

        Args:
            analysis: ConsensusAnalysis result
            has_sfp: Whether SFP pattern is present
            is_chasing: Whether entry would be chasing price

        Returns:
            Tuple of (should_reject, reason)
        """
        # Extreme consensus always rejects non-SFP trades
        if analysis.consensus_level >= self.extreme_consensus_threshold:
            if not has_sfp:
                return True, f"Extreme consensus ({analysis.consensus_level:.0f}%) - only SFP entries allowed"

        # High consensus raises the bar
        if analysis.consensus_level >= self.high_consensus_threshold:
            if is_chasing:
                return True, f"High consensus ({analysis.consensus_level:.0f}%) - no chasing allowed"

        # Check required expected R
        # (This would be checked at execution layer)

        return False, "Consensus check passed"
