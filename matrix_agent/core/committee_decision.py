"""
Committee Decision - Multi-Agent Voting System
===============================================
Layer 4 of the Matrix Agent system.

Committee Members:
- Macro Agent (veto power)
- Risk Agent (veto power)
- Liquidity Agent (direction suggestion)
- Anti-Consensus Agent (direction correction)

Rules:
- Any veto → NO TRADE
- Direction must come from SFP
- No "feeling long/short" allowed

Author: Matrix Agent
Version: 1.0.0
"""

import numpy as np
import pandas as pd
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import logging

from .models import (
    TradeSignal, 
    CommitteeResult, 
    CommitteeVote,
    Decision,
    VetoReason,
    SFPContext,
    MacroAnalysis,
    ConsensusAnalysis,
    RiskMetrics,
    TradeDirection,
    SignalSource
)

logger = logging.getLogger(__name__)


class CommitteeDecision:
    """
    Committee Decision System
    
    Multi-agent voting system that combines signals from all analysis layers:
    - Macro Gatekeeper (Veto Power)
    - Risk Governor (Veto Power)
    - SFP/Liquidity Detector (Direction)
    - Anti-Consensus Filter (Validation)
    
    Philosophy:
    "Direction must come from SFP, not feelings."
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize Committee Decision system.
        
        Args:
            config: Configuration dictionary with voting parameters
        """
        self.config = config or self._default_config()
        
        # Voting weights
        self.macro_weight = self.config.get('macro_weight', 0.30)
        self.risk_weight = self.config.get('risk_weight', 0.30)
        self.liquidity_weight = self.config.get('liquidity_weight', 0.25)
        self.consensus_weight = self.config.get('consensus_weight', 0.15)
        
        # Veto thresholds
        self.macro_veto_threshold = self.config.get('macro_veto_threshold', 0.3)
        self.risk_veto_threshold = self.config.get('risk_veto_threshold', 0.3)
        
        # Confidence thresholds
        self.min_approval_confidence = self.config.get('min_approval_confidence', 0.6)
        self.min_total_confidence = self.config.get('min_total_confidence', 0.5)
        
    def _default_config(self) -> Dict[str, Any]:
        """Return default configuration."""
        return {
            'macro_weight': 0.30,
            'risk_weight': 0.30,
            'liquidity_weight': 0.25,
            'consensus_weight': 0.15,
            'macro_veto_threshold': 0.3,
            'risk_veto_threshold': 0.3,
            'min_approval_confidence': 0.6,
            'min_total_confidence': 0.5,
            'require_sfp_direction': True,
            'allow_shorting': True,
            'allow_longing': True
        }
    
    def evaluate(self, signal: TradeSignal) -> CommitteeResult:
        """
        Evaluate trade signal through committee voting.
        
        Args:
            signal: Trade signal with all analysis layers populated
            
        Returns:
            CommitteeResult with voting decision
        """
        result = CommitteeResult()
        
        votes = []
        total_yes = 0
        total_weight = 0
        veto_applied = False
        veto_reason = None
        
        # 1. Macro Agent Vote (Veto Power)
        macro_vote, macro_confidence, macro_reasoning = self._vote_macro_agent(
            signal.macro_analysis
        )
        votes.append(CommitteeVote(
            member_name="Macro Agent",
            vote=macro_vote,
            confidence=macro_confidence,
            reasoning=macro_reasoning
        ))
        
        if macro_vote == Decision.REJECT:
            if macro_confidence >= self.macro_veto_threshold:
                veto_applied = True
                veto_reason = f"Macro Veto: {macro_reasoning}"
                logger.warning(f"Macro VETO applied: {macro_reasoning}")
        
        total_yes += macro_confidence if macro_vote == Decision.APPROVE else 0
        total_weight += self.macro_weight
        
        # 2. Risk Agent Vote (Veto Power)
        risk_vote, risk_confidence, risk_reasoning = self._vote_risk_agent(
            signal.risk_metrics
        )
        votes.append(CommitteeVote(
            member_name="Risk Agent",
            vote=risk_vote,
            confidence=risk_confidence,
            reasoning=risk_reasoning
        ))
        
        if risk_vote == Decision.REJECT:
            if risk_confidence >= self.risk_veto_threshold:
                veto_applied = True
                veto_reason = f"Risk Veto: {risk_reasoning}"
                logger.warning(f"Risk VETO applied: {risk_reasoning}")
        
        total_yes += risk_confidence if risk_vote == Decision.APPROVE else 0
        total_weight += self.risk_weight
        
        # 3. Liquidity Agent Vote (Direction from SFP)
        liquidity_vote, liquidity_confidence, liquidity_reasoning = self._vote_liquidity_agent(
            signal.sfp_context
        )
        votes.append(CommitteeVote(
            member_name="Liquidity Agent",
            vote=liquidity_vote,
            confidence=liquidity_confidence,
            reasoning=liquidity_reasoning
        ))
        
        total_yes += liquidity_confidence if liquidity_vote == Decision.APPROVE else 0
        total_weight += self.liquidity_weight
        
        # 4. Anti-Consensus Agent Vote (Validation)
        consensus_vote, consensus_confidence, consensus_reasoning = self._vote_consensus_agent(
            signal.consensus_analysis,
            signal.sfp_context
        )
        votes.append(CommitteeVote(
            member_name="Anti-Consensus Agent",
            vote=consensus_vote,
            confidence=consensus_confidence,
            reasoning=consensus_reasoning
        ))
        
        total_yes += consensus_confidence if consensus_vote == Decision.APPROVE else 0
        total_weight += self.consensus_weight
        
        result.votes = votes
        
        # Calculate final decision
        if veto_applied:
            result.decision = Decision.REJECT
            result.final_reasoning = veto_reason
            result.risk_score = 1.0  # Maximum risk
        else:
            # Calculate weighted confidence
            if total_weight > 0:
                weighted_confidence = total_yes / total_weight
            else:
                weighted_confidence = 0
            
            # Check minimum thresholds
            if weighted_confidence >= self.min_approval_confidence:
                result.decision = Decision.APPROVE
                result.final_reasoning = f"Approved with {weighted_confidence*100:.1f}% confidence"
            else:
                result.decision = Decision.REJECT
                result.final_reasoning = f"Confidence {weighted_confidence*100:.1f}% below {self.min_approval_confidence*100:.0f}% threshold"
        
        # Calculate expected R estimate from committee
        result.expected_r_estimate = self._estimate_expected_r(signal)
        
        # Calculate risk score
        result.risk_score = self._calculate_risk_score(signal, votes)
        
        return result
    
    def _vote_macro_agent(
        self,
        macro_analysis: Optional[MacroAnalysis]
    ) -> Tuple[Decision, float, str]:
        """
        Macro Agent voting logic.
        
        Returns:
            Tuple of(vote, confidence, reasoning)
        """
        if macro_analysis is None:
            return Decision.REJECT, 1.0, "No macro analysis provided"
        
        if not macro_analysis.is_approved:
            return Decision.REJECT, 0.9, macro_analysis.rejection_reason or "Macro not approved"
        
        # Approved - calculate confidence based on strength of approval
        confidence = 0.7
        
        # Higher confidence if multiple approval conditions met
        if macro_analysis.approval_condition:
            if "RSI pullback" in macro_analysis.approval_condition:
                confidence = 0.85
            elif "Extreme funding" in macro_analysis.approval_condition:
                confidence = 0.90
            elif "liquidity edge" in macro_analysis.approval_condition:
                confidence = 0.80
        
        return Decision.APPROVE, confidence, macro_analysis.approval_condition
    
    def _vote_risk_agent(
        self,
        risk_metrics: Optional[RiskMetrics]
    ) -> Tuple[Decision, float, str]:
        """
        Risk Agent voting logic.
        
        Returns:
            Tuple of (vote, confidence, reasoning)
        """
        if risk_metrics is None:
            return Decision.REJECT, 1.0, "No risk metrics provided"
        
        if risk_metrics.risk_warning:
            return Decision.REJECT, 0.8, risk_metrics.risk_warning
        
        if risk_metrics.current_drawdown >= 0.05:
            return Decision.REJECT, 0.7, f"Drawdown {risk_metrics.current_drawdown*100:.1f}% warning"
        
        if risk_metrics.is_safe_mode:
            return Decision.REJECT, 1.0, "System in safe mode"
        
        # Risk passed
        confidence = 0.9
        if risk_metrics.current_drawdown >= 0.03:
            confidence = 0.7  # Reduce confidence near drawdown limit
        
        return Decision.APPROVE, confidence, "Risk parameters acceptable"
    
    def _vote_liquidity_agent(
        self,
        sfp_context: Optional[SFPContext]
    ) -> Tuple[Decision, float, str]:
        """
        Liquidity Agent voting logic - CORE requirement.
        
        Direction MUST come from SFP. No SFP = No trade.
        
        Returns:
            Tuple of (vote, confidence, reasoning)
        """
        if sfp_context is None:
            return Decision.REJECT, 1.0, "No SFP pattern - direction required from SFP"
        
        if not sfp_context.is_valid:
            return Decision.REJECT, 0.9, f"Invalid SFP: {sfp_context.invalidation_reason}"
        
        # Validate SFP
        if sfp_context.risk_reward_ratio < 2.0:
            return Decision.REJECT, 0.8, f"SFP RR too low: {sfp_context.risk_reward_ratio:.2f}"
        
        # Calculate confidence based on SFP quality
        confidence = 0.75
        
        # Higher confidence for stronger signals
        if sfp_context.risk_reward_ratio >= 3.0:
            confidence = 0.90
        elif sfp_context.risk_reward_ratio >= 2.5:
            confidence = 0.85
        elif sfp_context.risk_reward_ratio >= 2.0:
            confidence = 0.75
        
        # Determine direction from SFP
        if sfp_context.pattern_type == 'bullish_sfp':
            direction_str = "LONG from bullish SFP"
        elif sfp_context.pattern_type == 'bearish_sfp':
            direction_str = "SHORT from bearish SFP"
        else:
            direction_str = "Unknown SFP direction"
        
        return Decision.APPROVE, confidence, f"{direction_str} at {sfp_context.liquidity_zone:.4f}"
    
    def _vote_consensus_agent(
        self,
        consensus_analysis: Optional[ConsensusAnalysis],
        sfp_context: Optional[SFPContext]
    ) -> Tuple[Decision, float, str]:
        """
        Anti-Consensus Agent voting logic.
        
        Returns:
            Tuple of (vote, confidence, reasoning)
        """
        if consensus_analysis is None:
            return Decision.REJECT, 0.5, "No consensus analysis provided"
        
        # Check if consensus allows trading
        if not consensus_analysis.can_trade:
            return Decision.REJECT, 0.9, consensus_analysis.warning_reason or "Consensus prevents trading"
        
        # High consensus requires higher confidence
        if consensus_analysis.is_high_consensus:
            if sfp_context is None:
                return Decision.REJECT, 0.85, "High consensus requires SFP reversal"
            
            if consensus_analysis.consensus_level >= 90:
                return Decision.REJECT, 0.7, f"Extreme consensus ({consensus_analysis.consensus_level:.0f}%)"
            
            confidence = 0.6  # Lower confidence in high consensus
        else:
            confidence = 0.8  # Normal conditions
        
        return Decision.APPROVE, confidence, f"Consensus level: {consensus_analysis.consensus_level:.0f}%"
    
    def _estimate_expected_r(self, signal: TradeSignal) -> float:
        """
        Estimate expected R from signal components.
        
        Returns:
            Estimated expected R value
        """
        base_rr = 0
        
        if signal.sfp_context:
            base_rr = signal.sfp_context.risk_reward_ratio
        
        # Adjust based on other factors
        adjustment = 1.0
        
        if signal.macro_analysis and signal.macro_analysis.is_approved:
            adjustment *= 1.1  # Macro confirmation boost
        
        if signal.consensus_analysis and signal.consensus_analysis.is_high_consensus:
            adjustment *= 0.8  # Reduce for high consensus
        
        if signal.risk_metrics and signal.risk_metrics.current_drawdown >= 0.03:
            adjustment *= 0.9  # Reduce in drawdown
        
        return base_rr * adjustment
    
    def _calculate_risk_score(
        self,
        signal: TradeSignal,
        votes: List[CommitteeVote]
    ) -> float:
        """
        Calculate overall risk score from committee evaluation.
        
        Returns:
            Risk score (0-1, where 1 = highest risk)
        """
        risk_factors = []
        
        # No SFP = high risk
        if signal.sfp_context is None:
            risk_factors.append(0.8)
        
        # Macro not approved = high risk
        macro_vote = next((v for v in votes if v.member_name == "Macro Agent"), None)
        if macro_vote and macro_vote.vote == Decision.REJECT:
            risk_factors.append(0.7)
        
        # High consensus = elevated risk
        if signal.consensus_analysis and signal.consensus_analysis.is_high_consensus:
            risk_factors.append(0.3)
        
        # High drawdown = elevated risk
        if signal.risk_metrics and signal.risk_metrics.current_drawdown >= 0.03:
            risk_factors.append(0.2)
        
        # Low confidence votes = elevated risk
        low_confidence_votes = [v for v in votes if v.confidence < 0.6]
        if low_confidence_votes:
            risk_factors.append(0.15 * len(low_confidence_votes))
        
        if not risk_factors:
            return 0.1  # Low risk default
        
        return min(sum(risk_factors), 1.0)
    
    def get_committee_summary(self, result: CommitteeResult) -> Dict[str, Any]:
        """
        Generate committee summary for reporting.
        
        Args:
            result: CommitteeResult to summarize
            
        Returns:
            Summary dictionary
        """
        return {
            'decision': result.decision.value,
            'final_reasoning': result.final_reasoning,
            'risk_score': result.risk_score,
            'expected_r_estimate': result.expected_r_estimate,
            'votes': [
                {
                    'member': v.member_name,
                    'vote': v.vote.value,
                    'confidence': v.confidence,
                    'reasoning': v.reasoning
                }
                for v in result.votes
            ],
            'timestamp': result.timestamp.isoformat()
        }
