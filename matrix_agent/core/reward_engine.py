"""
Reward Engine - Post-Trade Reinforcement Learning
==================================================
Layer 7 of the Matrix Agent system.

Reward Logic:
- Reward whether worth betting, not whether profitable
- Reward NO TRADE decisions
- Strongly penalize non-A+ executions

Core Principle:
- Non-A+ execution → Severe negative reward
- Correct NO TRADE → Positive reward

Author: Matrix Agent
Version: 1.0.0
"""

import numpy as np
import pandas as pd
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
import json

from .models import (
    TradeSignal, 
    ExecutionResult, 
    PerformanceMetrics,
    VetoReason,
    Decision
)

logger = logging.getLogger(__name__)


@dataclass
class TradeEvaluation:
    """Detailed trade evaluation for reinforcement learning."""
    trade_id: str
    pair: str
    decision: str  # APPROVE/REJECT
    execution_quality: str  # A+, A, B, C, D
    expected_r: float
    actual_r: float
    profit_pct: float
    duration_minutes: float
    mistakes: List[str]
    timestamp: datetime
    reward_score: float
    learning_points: List[str]


class RewardEngine:
    """
    Reward Engine - Post-Trade Reinforcement Learning
    
    Evaluates trading decisions and executions to provide feedback:
    - Rewards good decision-making (not just profitable trades)
    - Penalizes poor executions and decision errors
    - Identifies patterns for improvement
    
    Philosophy:
    "Reward whether worth betting, not whether profitable."
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize Reward Engine.
        
        Args:
            config: Configuration dictionary with reward parameters
        """
        self.config = config or self._default_config()
        
        # Reward weights
        self.no_trade_reward = self.config.get('no_trade_reward', 1.0)
        self.good_trade_reward = self.config.get('good_trade_reward', 0.5)
        self.bad_trade_penalty = self.config.get('bad_trade_penalty', -1.0)
        self.non_a_plus_penalty = self.config.get('non_a_plus_penalty', -0.5)
        
        # Quality thresholds
        self.a_plus_threshold = self.config.get('a_plus_threshold', 0.95)
        self.good_execution_threshold = self.config.get('good_execution_threshold', 0.80)
        
        # Performance tracking
        self.trade_history: List[TradeEvaluation] = []
        self.weekly_metrics: Dict[str, PerformanceMetrics] = {}
        
    def _default_config(self) -> Dict[str, Any]:
        """Return default configuration."""
        return {
            'no_trade_reward': 1.0,
            'good_trade_reward': 0.5,
            'bad_trade_penalty': -1.0,
            'non_a_plus_penalty': -0.5,
            'a_plus_threshold': 0.95,
            'good_execution_threshold': 0.80,
            'min_expected_r': 3.0,
            'reward_window_trades': 50
        }
    
    def evaluate_trade(
        self,
        signal: TradeSignal,
        execution: ExecutionResult,
        actual_profit_pct: float = 0.0
    ) -> TradeEvaluation:
        """
        Evaluate a completed trade and calculate reward.
        
        Args:
            signal: Original trade signal
            execution: Execution result
            actual_profit_pct: Actual profit/loss percentage
            
        Returns:
            TradeEvaluation with reward score
        """
        evaluation = TradeEvaluation(
            trade_id=execution.trade_id,
            pair=signal.pair,
            decision=signal.decision.value,
            execution_quality=execution.execution_quality,
            expected_r=signal.expected_r,
            actual_r=actual_profit_pct / abs(signal.entry_price - signal.stop_loss) * signal.entry_price if signal.entry_price != signal.stop_loss else 0,
            profit_pct=actual_profit_pct,
            duration_minutes=execution.duration_minutes,
            mistakes=execution.mistakes,
            timestamp=datetime.now(),
            reward_score=0.0,
            learning_points=[]
        )
        
        # Calculate reward score
        reward_score = self._calculate_reward(evaluation, signal)
        evaluation.reward_score = reward_score
        
        # Generate learning points
        evaluation.learning_points = self._generate_learning_points(evaluation, signal)
        
        # Store in history
        self.trade_history.append(evaluation)
        
        # Log evaluation
        logger.info(f"Trade Evaluation: {evaluation.pair} {evaluation.decision}")
        logger.info(f"  Execution Quality: {evaluation.execution_quality}")
        logger.info(f"  Expected R: {evaluation.expected_r:.2f}, Actual R: {evaluation.actual_r:.2f}")
        logger.info(f"  Reward Score: {evaluation.reward_score:.2f}")
        if evaluation.learning_points:
            logger.info(f"  Learning Points: {', '.join(evaluation.learning_points)}")
        
        return evaluation
    
    def evaluate_no_trade(self, signal: TradeSignal) -> TradeEvaluation:
        """
        Evaluate a NO TRADE decision.
        
        Args:
            signal: Rejected trade signal
            
        Returns:
            TradeEvaluation for no-trade decision
        """
        evaluation = TradeEvaluation(
            trade_id=f"notrade_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            pair=signal.pair,
            decision="REJECT",
            execution_quality="N/A",
            expected_r=signal.expected_r,
            actual_r=0.0,
            profit_pct=0.0,
            duration_minutes=0.0,
            mistakes=[],
            timestamp=datetime.now(),
            reward_score=0.0,
            learning_points=[]
        )
        
        # Reward NO TRADE decisions
        reward_score = self._calculate_no_trade_reward(signal)
        evaluation.reward_score = reward_score
        
        # Generate learning points
        evaluation.learning_points = self._generate_no_trade_learning_points(signal)
        
        # Store in history
        self.trade_history.append(evaluation)
        
        logger.info(f"NO TRADE Evaluation: {evaluation.pair}")
        logger.info(f"  Veto Reason: {signal.veto_reason}")
        logger.info(f"  Reward Score: {evaluation.reward_score:.2f}")
        
        return evaluation
    
    def _calculate_reward(
        self,
        evaluation: TradeEvaluation,
        signal: TradeSignal
    ) -> float:
        """
        Calculate reward score for a trade.
        
        Args:
            evaluation: Trade evaluation
            signal: Original trade signal
            
        Returns:
            Reward score (positive = good, negative = bad)
        """
        reward = 0.0
        
        # 1. Execution quality reward/penalty
        if evaluation.execution_quality == "A+":
            reward += 1.0
        elif evaluation.execution_quality == "A":
            reward += 0.5
        elif evaluation.execution_quality == "B":
            reward += 0.0
        elif evaluation.execution_quality == "C":
            reward += -0.3
        else:  # D
            reward += -0.5
        
        # 2. Non-A+ penalty (if it was supposed to be A+)
        if evaluation.execution_quality not in ["A+", "A"]:
            reward += self.non_a_plus_penalty
        
        # 3. Expected R quality
        if evaluation.expected_r >= 4:
            reward += 0.3
        elif evaluation.expected_r >= 3:
            reward += 0.1
        else:
            reward += -0.2  # Penalty for low expected R
        
        # 4. Actual vs Expected performance
        if evaluation.actual_r >= evaluation.expected_r * 0.8:
            reward += 0.2  # Met expectations
        elif evaluation.actual_r >= 0:
            reward += 0.0  # Profitable but below expectations
        else:
            reward += -0.3  # Loss
        
        # 5. Mistake penalties
        for mistake in evaluation.mistakes:
            if "chasing" in mistake.lower():
                reward += -0.5
            elif "late" in mistake.lower():
                reward += -0.3
            elif "early" in mistake.lower():
                reward += -0.3
            else:
                reward += -0.1
        
        # 6. Committee consensus reward
        if evaluation.execution_quality in ["A+", "A"]:
            # Good execution in high consensus scenario
            if signal.consensus_analysis and signal.consensus_analysis.is_high_consensus:
                reward += 0.2
        
        # 7. SFP quality bonus
        if signal.sfp_context:
            if signal.sfp_context.risk_reward_ratio >= 3:
                reward += 0.2
            elif signal.sfp_context.risk_reward_ratio >= 2.5:
                reward += 0.1
        
        return reward
    
    def _calculate_no_trade_reward(self, signal: TradeSignal) -> float:
        """
        Calculate reward for NO TRADE decision.
        
        Args:
            signal: Rejected trade signal
            
        Returns:
            Reward score
        """
        reward = 0.0
        
        # Base reward for correct rejection
        reward += self.no_trade_reward * 0.5
        
        # Bonus for veto reasons that saved money
if signal.veto_reason:
            if signal.veto_reason == VetoReason.NO_SFP:
                reward += 0.3  # Correctly rejected no-SFP
            elif signal.veto_reason == VetoReason.CONSENSUS_TOO_HIGH:
                reward += 0.3  # Correctly avoided high consensus
            elif signal.veto_reason == VetoReason.RISK_TOO_HIGH:
                reward += 0.3  # Correctly avoided high risk
            elif signal.veto_reason == VetoReason.DRAWDOWN_LIMIT:
                reward += 0.4  # Critical drawdown protection
            elif signal.veto_reason == VetoReason.EXPECTED_R_TOO_LOW:
                reward += 0.2  # Correctly rejected low R
        
        # Bonus for rejection with strong macro confirmation
        if signal.macro_analysis and not signal.macro_analysis.is_approved:
            reward += 0.2
        
        # Penalty for incorrect rejections (missed opportunities)
        # This would require historical data to determine
        
        return reward
    
    def _generate_learning_points(
        self,
        evaluation: TradeEvaluation,
        signal: TradeSignal
    ) -> List[str]:
        """
        Generate learning points from trade evaluation.
        
        Args:
            evaluation: Trade evaluation
            signal: Original trade signal
            
        Returns:
            List of learning point strings
        """
        points = []
        
        # Execution quality points
        if evaluation.execution_quality not in ["A+", "A"]:
            points.append(f"Execution quality {evaluation.execution_quality} needs improvement")
        
        # Expected R points
        if evaluation.expected_r < 3.0:
            points.append(f"Expected R {evaluation.expected_r:.2f} below 3.0 threshold")
        
        # Profitability points
        if evaluation.profit_pct < 0 and evaluation.actual_r > 0:
            points.append("Profitable but stop loss hit - review SL placement")
        elif evaluation.profit_pct < 0:
            points.append("Loss - analyze if this was a structural error")
        
        # Mistake points
        for mistake in evaluation.mistakes:
            points.append(f"Error: {mistake}")
        
        # Pattern recognition
        if evaluation.execution_quality in ["A+", "A"]:
            if signal.sfp_context and signal.sfp_context.risk_reward_ratio >= 3:
                points.append("High quality SFP execution - identify similar setups")
        
        # Committee points
        if signal.confidence < 0.7:
            points.append("Low confidence signal - review committee decision")
        
        return points
    
    def _generate_no_trade_learning_points(self, signal: TradeSignal) -> List[str]:
        """
        Generate learning points from NO TRADE decision.
        
        Args:
            signal: Rejected trade signal
            
        Returns:
            List of learning point strings
        """
        points = []
        
        # Veto reason analysis
        if signal.veto_reason:
            points.append(f"Correct veto: {signal.veto_reason.value}")
        
        # Missing components
        if not signal.sfp_context:
            points.append("Missing SFP - ensure liquidity hunter is working")
        
        if not signal.macro_analysis or not signal.macro_analysis.is_approved:
            points.append("Macro not approved - verify macro conditions")
        
        # Risk warning
        if signal.risk_metrics and signal.risk_metrics.risk_warning:
            points.append(f"Risk warning: {signal.risk_metrics.risk_warning}")
        
        # Consensus check
        if signal.consensus_analysis and signal.consensus_analysis.is_high_consensus:
            points.append("High consensus - good rejection unless SFP reversal")
        
        return points
    
    def calculate_performance_metrics(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> PerformanceMetrics:
        """
        Calculate performance metrics for a period.
        
        Args:
            start_date: Start of period (default: all history)
            end_date: End of period (default: now)
            
        Returns:
            PerformanceMetrics object
        """
        # Filter trades by date
        trades = self.trade_history
        
        if start_date:
            trades = [t for t in trades if t.timestamp >= start_date]
        if end_date:
            trades = [t for t in trades if t.timestamp <= end_date]
        
        # Calculate metrics
        total_trades = len([t for t in trades if t.decision == "APPROVE"])
        no_trade_decisions = len([t for t in trades if t.decision == "REJECT"])
        
        winning_trades = len([t for t in trades if t.profit_pct > 0])
        losing_trades = len([t for t in trades if t.profit_pct < 0])
        
        win_rate = winning_trades / total_trades if total_trades > 0 else 0
        
        # Calculate returns
        profits = [t.profit_pct for t in trades if t.decision == "APPROVE"]
        total_return = sum(profits) if profits else 0
        
        # Calculate expectancy
        avg_win = np.mean([t.profit_pct for t in trades if t.profit_pct > 0]) if winning_trades > 0 else 0
        avg_loss = abs(np.mean([t.profit_pct for t in trades if t.profit_pct < 0])) if losing_trades > 0 else 0
        
        expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)
        
        # Calculate profit factor
        gross_profit = sum([t.profit_pct for t in trades if t.profit_pct > 0])
        gross_loss = abs(sum([t.profit_pct for t in trades if t.profit_pct < 0]))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        # Average trade duration
        durations = [t.duration_minutes for t in trades if t.duration_minutes > 0]
        avg_duration = np.mean(durations) if durations else 0
        
        # NO TRADE ratio
        no_trade_ratio = no_trade_decisions / (total_trades + no_trade_decisions) if (total_trades + no_trade_decisions) > 0 else 0
        
        # A+ execution ratio
        a_plus_trades = [t for t in trades if t.execution_quality in ["A+", "A"] and t.decision == "APPROVE"]
        a_plus_executions = len(a_plus_trades)
        non_a_plus = total_trades - a_plus_executions
        a_plus_ratio = a_plus_executions / total_trades if total_trades > 0 else 0
        
        # Average expected R
        expected_r_values = [t.expected_r for t in trades if t.decision == "APPROVE"]
        avg_expected_r = np.mean(expected_r_values) if expected_r_values else 0
        
        # Find top pattern
        pattern_counts = {}
        for t in trades:
            if t.decision == "APPROVE":
                pattern = t.execution_quality  # Simplified
                pattern_counts[pattern] = pattern_counts.get(pattern, 0) + 1
        top_pattern = max(pattern_counts, key=pattern_counts.get) if pattern_counts else None
        
        metrics = PerformanceMetrics(
            period_start=start_date or datetime.now() - timedelta(days=7),
            period_end=end_date or datetime.now(),
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            total_return=total_return,
            max_drawdown=0,  # Would need equity curve calculation
            profit_factor=profit_factor,
            expectancy=expectancy,
            average_trade_duration=avg_duration,
            no_trade_decisions=no_trade_decisions,
            a_plus_executions=a_plus_executions,
            non_a_plus_executions=non_a_plus,
            avg_expected_r=avg_expected_r,
            top_pattern=top_pattern
        )
        
        return metrics
    
    def get_system_health(self) -> Dict[str, Any]:
        """
        Get system health status based on recent performance.
        
        Returns:
            Health status dictionary
        """
        recent_trades = self.trade_history[-self.config.get('reward_window_trades', 50):]
        
        if not recent_trades:
            return {
                'status': 'UNKNOWN',
                'message': 'No trade history'
            }
        
        # Calculate recent metrics
        recent_rewards = [t.reward_score for t in recent_trades]
        avg_reward = np.mean(recent_rewards)
        
        no_trade_ratio = len([t for t in recent_trades if t.decision == "REJECT"]) / len(recent_trades)
        
        a_plus_ratio = len([t for t in recent_trades if t.execution_quality in ["A+", "A"]]) / len(recent_trades)
        
        # Determine health
        if avg_reward >= 0.5 and a_plus_ratio >= 0.6:
            status = "HEALTHY"
            message = f"A+ ratio: {a_plus_ratio*100:.1f}%, Avg reward: {avg_reward:.2f}"
        elif avg_reward >= 0:
            status = "CAUTION"
            message = f"A+ ratio: {a_plus_ratio*100:.1f}%, Avg reward: {avg_reward:.2f}"
        else:
            status = "WARNING"
            message = f"Low A+ ratio: {a_plus_ratio*100:.1f}%, Negative reward: {avg_reward:.2f}"
        
        return {
            'status': status,
            'message': message,
            'avg_reward': avg_reward,
            'no_trade_ratio': no_trade_ratio,
            'a_plus_ratio': a_plus_ratio,
            'total_trades': len(recent_trades)
        }
    
    def get_learning_summary(self) -> Dict[str, Any]:
        """
        Get summary of learning from recent trades.
        
        Returns:
            Learning summary dictionary
        """
        recent_trades = self.trade_history[-50:]
        
        # Collect all learning points
        all_points = []
        for trade in recent_trades:
            all_points.extend(trade.learning_points)
        
        # Count point occurrences
        point_counts = {}
        for point in all_points:
            point_counts[point] = point_counts.get(point, 0) + 1
        
        # Sort by frequency
        top_points = sorted(point_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        
        # Identify common mistakes
        mistakes = [point for point in all_points if "Error" in point or "needs improvement" in point]
        mistake_counts = {}
        for mistake in mistakes:
            mistake_counts[mistake] = mistake_counts.get(mistake, 0) + 1
        top_mistakes = sorted(mistake_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        
        return {
            'total_learning_points': len(all_points),
            'top_learning_points': [p for p, c in top_points],
            'common_mistakes': [m for m, c in top_mistakes],
            'improvement_areas': [p for p, c in top_points if "needs" in p.lower() or "error" in p.lower()]
        }
