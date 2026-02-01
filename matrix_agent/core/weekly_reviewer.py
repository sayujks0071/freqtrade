"""
Weekly Review Agent - AI Performance Reviewer
==============================================
Layer 8 of the Matrix Agent system.

Weekly Review Requirements (Must execute every 7 days):

Checklist:
1. Is NO TRADE ratio ≥ 60%?
2. Were there any non-A+ executions?
3. Is A+ average Expected R ≥ 3?
4. Which pattern contributed most profit?

Red Line Mechanism:
- Non-A+ executions ≥ 2 → System degradation warning
- 2 consecutive weeks A+ failure → SAFE MODE

Author: Matrix Agent
Version: 1.0.0
"""

import numpy as np
import pandas as pd
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta, date
import logging
import json

from .models import (
    PerformanceMetrics, 
    TradeSignal, 
    ExecutionResult,
    Decision
)
from .reward_engine import RewardEngine, TradeEvaluation

logger = logging.getLogger(__name__)


@dataclass
class WeeklyReport:
    """Weekly performance report."""
    week_start: datetime
    week_end: datetime
    metrics: PerformanceMetrics
    checklist_results: Dict[str, Tuple[bool, str]]
    red_line_status: str
    recommendations: List[str]
    pattern_analysis: Dict[str, Any]
    risk_assessment: Dict[str, Any]
    overall_score: float
    status: str  # EXCELLENT, GOOD, WARNING, CRITICAL
    generated_at: datetime


class WeeklyReviewer:
    """
    Weekly Review Agent - AI Performance Reviewer
    
    Performs comprehensive weekly review of trading performance:
    - Validates checklist requirements
    - Identifies patterns and trends
    - Triggers red line warnings
    - Generates improvement recommendations
    
    Philosophy:
    "Continuous improvement through systematic review."
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize Weekly Reviewer.
        
        Args:
            config: Configuration dictionary with review parameters
        """
        self.config = config or self._default_config()
        
        # Checklist thresholds
        self.min_no_trade_ratio = self.config.get('min_no_trade_ratio', 0.60)  # 60%
        self.min_expected_r = self.config.get('min_expected_r', 3.0)
        self.max_non_a_plus = self.config.get('max_non_a_plus', 2)
        
        # Red line thresholds
        self.red_line_non_a_plus = self.config.get('red_line_non_a_plus', 2)
        self.consecutive_failures_for_safe_mode = self.config.get('consecutive_failures_for_safe_mode', 2)
        
        # Performance scoring weights
        self.weights = {
            'no_trade_ratio': 0.25,
            'a_plus_ratio': 0.25,
            'expected_r': 0.20,
            'profit_factor': 0.15,
            'win_rate': 0.15
        }
        
        # State tracking
        self.weekly_reports: List[WeeklyReport] = []
        self.consecutive_a_plus_failures = 0
        self.last_review_date: Optional[datetime] = None
        
    def _default_config(self) -> Dict[str, Any]:
        """Return default configuration."""
        return {
            'min_no_trade_ratio': 0.60,      # 60% no-trade ratio required
            'min_expected_r': 3.0,           # Min 3R average
            'max_non_a_plus': 2,             # Max 2 non-A+ executions
            'red_line_non_a_plus': 2,        # Red line at 2 non-A+
            'consecutive_failures_for_safe_mode': 2,
            'review_day': 'sunday',          # Day of week for reviews
            'max_drawdown_threshold': 0.05,  # 5% max drawdown
            'min_win_rate': 0.30             # Min 30% win rate
        }
    
    def run_weekly_review(
        self,
        reward_engine: RewardEngine,
        week_start: Optional[datetime] = None
    ) -> WeeklyReport:
        """
        Run weekly review and generate report.
        
        Args:
            reward_engine: RewardEngine with trade history
            week_start: Start of review week (default: 7 days ago)
            
        Returns:
            WeeklyReport with findings and recommendations
        """
        if week_start is None:
            week_start = datetime.now() - timedelta(days=7)
        
        week_end = datetime.now()
        
        # Get performance metrics for the week
        metrics = reward_engine.calculate_performance_metrics(
            start_date=week_start,
            end_date=week_end
        )
        
        # Run checklist validation
        checklist_results = self._run_checklist(metrics, reward_engine)
        
        # Check red line status
        red_line_status = self._check_red_lines(metrics, reward_engine)
        
        # Analyze patterns
        pattern_analysis = self._analyze_patterns(reward_engine)
        
        # Generate recommendations
        recommendations = self._generate_recommendations(
            metrics, checklist_results, pattern_analysis
        )
        
        # Perform risk assessment
        risk_assessment = self._assess_risk(metrics)
        
        # Calculate overall score
        overall_score = self._calculate_overall_score(metrics, checklist_results)
        
        # Determine status
        status = self._determine_status(overall_score, red_line_status)
        
        # Build report
        report = WeeklyReport(
            week_start=week_start,
            week_end=week_end,
            metrics=metrics,
            checklist_results=checklist_results,
            red_line_status=red_line_status,
            recommendations=recommendations,
            pattern_analysis=pattern_analysis,
            risk_assessment=risk_assessment,
            overall_score=overall_score,
            status=status,
            generated_at=datetime.now()
        )
        
        # Store report
        self.weekly_reports.append(report)
        self.last_review_date = datetime.now()
        
        # Update consecutive failure counter
        if not self._checklist_passed(checklist_results):
            self.consecutive_a_plus_failures += 1
        else:
            self.consecutive_a_plus_failures = 0
        
        # Log report summary
        logger.info("=" * 60)
        logger.info("WEEKLY REVIEW REPORT")
        logger.info("=" * 60)
        logger.info(f"Week: {week_start.strftime('%Y-%m-%d')} to {week_end.strftime('%Y-%m-%d')}")
        logger.info(f"Status: {report.status}")
        logger.info(f"Overall Score: {report.overall_score:.2f}/100")
        logger.info(f"Red Line Status: {report.red_line_status}")
        logger.info(f"NO TRADE Ratio: {metrics.no_trade_ratio*100:.1f}% (Target: {self.min_no_trade_ratio*100:.0f}%)")
        logger.info(f"A+ Executions: {metrics.a_plus_executions}/{metrics.total_trades}")
        logger.info(f"Avg Expected R: {metrics.avg_expected_r:.2f} (Target: {self.min_expected_r:.1f})")
        logger.info(f"Win Rate: {metrics.win_rate*100:.1f}%")
        logger.info(f"Profit Factor: {metrics.profit_factor:.2f}")
        if report.recommendations:
            logger.info("Recommendations:")
            for rec in report.recommendations:
                logger.info(f"  - {rec}")
        logger.info("=" * 60)
        
        return report
    
    def _run_checklist(
        self,
        metrics: PerformanceMetrics,
        reward_engine: RewardEngine
    ) -> Dict[str, Tuple[bool, str]]:
        """
        Run weekly checklist validation.
        
        Checklist:
        1. Is NO TRADE ratio ≥ 60%?
        2. Were there any non-A+ executions?
        3. Is A+ average Expected R ≥ 3?
        4. Which pattern contributed most profit?
        
        Returns:
            Dictionary with checklist item results
        """
        results = {}
        
        # Check 1: NO TRADE ratio
        no_trade_passed = metrics.no_trade_ratio >= self.min_no_trade_ratio
        results['no_trade_ratio'] = (
            no_trade_passed,
            f"NO TRADE ratio: {metrics.no_trade_ratio*100:.1f}% (Target: {self.min_no_trade_ratio*100:.0f}%)"
        )
        
        # Check 2: Non-A+ executions
        non_a_plus_count = metrics.non_a_plus_executions
        non_a_plus_passed = non_a_plus_count <= self.max_non_a_plus
        results['non_a_plus_executions'] = (
            non_a_plus_passed,
            f"Non-A+ executions: {non_a_plus_count} (Max: {self.max_non_a_plus})"
        )
        
        # Check 3: Expected R for A+ trades
        a_plus_trades = [t for t in reward_engine.trade_history 
                        if t.execution_quality in ["A+", "A"]]
        if a_plus_trades:
            avg_expected_r = np.mean([t.expected_r for t in a_plus_trades])
        else:
            avg_expected_r = 0
        expected_r_passed = avg_expected_r >= self.min_expected_r
        results['expected_r'] = (
            expected_r_passed,
            f"A+ avg Expected R: {avg_expected_r:.2f} (Target: {self.min_expected_r:.1f})"
        )
        
        # Check 4: Top profitable pattern
        top_pattern = self._identify_top_pattern(reward_engine)
        results['top_pattern'] = (
            True,  # Always passes, just informational
            f"Top pattern: {top_pattern}"
        )
        
        return results
    
    def _check_red_lines(
        self,
        metrics: PerformanceMetrics,
        reward_engine: RewardEngine
    ) -> str:
        """
        Check red line conditions.
        
        Red Line Mechanism:
        - Non-A+ executions ≥ 2 → System degradation warning
        - 2 consecutive weeks A+ failure → SAFE MODE
        
        Returns:
            Red line status string
        """
        # Check non-A+ count
        if metrics.non_a_plus_executions >= self.red_line_non_a_plus:
            return "WARNING: Non-A+ executions exceed limit"
        
        # Check consecutive failures
        if self.consecutive_a_plus_failures >= self.consecutive_failures_for_safe_mode:
            return "CRITICAL: Consecutive failures - SAFE MODE TRIGGERED"
        
        # Check other red line conditions
        if metrics.max_drawdown > self.config.get('max_drawdown_threshold', 0.05):
            return f"WARNING: Max drawdown {metrics.max_drawdown*100:.1f}% exceeds threshold"
        
        if metrics.profit_factor < 0.5:
            return "WARNING: Profit factor critically low"
        
        return "OK: All red lines clear"
    
    def _analyze_patterns(self, reward_engine: RewardEngine) -> Dict[str, Any]:
        """
        Analyze trading patterns from recent trades.
        
        Args:
            reward_engine: RewardEngine with trade history
            
        Returns:
            Pattern analysis dictionary
        """
        recent_trades = reward_engine.trade_history[-50:]
        
        if not recent_trades:
            return {'status': 'No data available'}
        
        # Analyze by execution quality
        quality_stats = {}
        for quality in ["A+", "A", "B", "C", "D"]:
            trades = [t for t in recent_trades if t.execution_quality == quality]
            if trades:
                quality_stats[quality] = {
                    'count': len(trades),
                    'avg_profit': np.mean([t.profit_pct for t in trades]),
                    'avg_expected_r': np.mean([t.expected_r for t in trades]),
                    'total_reward': np.sum([t.reward_score for t in trades])
                }
        
        # Analyze by decision type
        decision_stats = {
            'approved': {
                'count': len([t for t in recent_trades if t.decision == "APPROVE"]),
                'avg_profit': np.mean([t.profit_pct for t in recent_trades if t.decision == "APPROVE"]) or 0
            },
            'rejected': {
                'count': len([t for t in recent_trades if t.decision == "REJECT"]),
                'avg_reward': np.mean([t.reward_score for t in recent_trades if t.decision == "REJECT"]) or 0
            }
        }
        
        # Analyze by time (if available)
        hourly_distribution = {}
        for trade in recent_trades:
            hour = trade.timestamp.hour
            if hour not in hourly_distribution:
                hourly_distribution[hour] = {'count': 0, 'profit': 0}
            hourly_distribution[hour]['count'] += 1
            hourly_distribution[hour]['profit'] += trade.profit_pct
        
        return {
            'quality_stats': quality_stats,
            'decision_stats': decision_stats,
            'hourly_distribution': hourly_distribution,
            'total_trades_analyzed': len(recent_trades)
        }
    
    def _generate_recommendations(
        self,
        metrics: PerformanceMetrics,
        checklist_results: Dict[str, Tuple[bool, str]],
        pattern_analysis: Dict[str, Any]
    ) -> List[str]:
        """
        Generate improvement recommendations.
        
        Args:
            metrics: Performance metrics
            checklist_results: Checklist validation results
            pattern_analysis: Pattern analysis results
            
        Returns:
            List of recommendation strings
        """
        recommendations = []
        
        # NO TRADE ratio recommendations
        no_trade_passed, _ = checklist_results.get('no_trade_ratio', (False, ""))
        if not no_trade_passed:
            recommendations.append(
                "Increase NO TRADE discipline - reject more marginal setups"
            )
        
        # Non-A+ execution recommendations
        non_a_plus_passed, _ = checklist_results.get('non_a_plus_executions', (True, ""))
        if not non_a_plus_passed:
            recommendations.append(
                "Improve execution quality - review entry timing and position sizing"
            )
        
        # Expected R recommendations
        expected_r_passed, _ = checklist_results.get('expected_r', (True, ""))
        if not expected_r_passed:
            recommendations.append(
                "Raise Expected R threshold - only take 3R+ setups in normal conditions"
            )
        
        # Win rate recommendations
        if metrics.win_rate < 0.3:
            recommendations.append(
                "Win rate below 30% - review entry criteria and market selection"
            )
        
        # Profit factor recommendations
        if metrics.profit_factor < 1.0:
            if metrics.profit_factor < 0.5:
                recommendations.append(
                    "Critical: Profit factor below 0.5 - consider pausing trading"
                )
            else:
                recommendations.append(
                    "Profit factor below 1.0 - tighten stop losses or improve entry"
                )
        
        # Drawdown recommendations
        if metrics.max_drawdown > 0.05:
            recommendations.append(
                f"Max drawdown {metrics.max_drawdown*100:.1f}% exceeds 5% - reduce position sizes"
            )
        
        # Pattern-based recommendations
        quality_stats = pattern_analysis.get('quality_stats', {})
        if 'D' in quality_stats or 'C' in quality_stats:
            recommendations.append(
                "Eliminate C/D quality trades - only execute A+ setups"
            )
        
        # Positive reinforcement
        if all([no_trade_passed, non_a_plus_passed, expected_r_passed]):
            recommendations.append(
                "Excellent week - maintain current discipline"
            )
        
        return recommendations
    
    def _assess_risk(self, metrics: PerformanceMetrics) -> Dict[str, Any]:
        """
        Perform risk assessment.
        
        Args:
            metrics: Performance metrics
            
        Returns:
            Risk assessment dictionary
        """
        risk_factors = []
        risk_score = 0
        
        # Drawdown risk
        if metrics.max_drawdown > 0.08:
            risk_factors.append("Critical drawdown (>8%)")
            risk_score += 30
        elif metrics.max_drawdown > 0.05:
            risk_factors.append("High drawdown (>5%)")
            risk_score += 20
        
        # Win rate risk
        if metrics.win_rate < 0.20:
            risk_factors.append("Critical win rate (<20%)")
            risk_score += 25
        elif metrics.win_rate < 0.30:
            risk_factors.append("Low win rate (<30%)")
            risk_score += 15
        
        # Profit factor risk
        if metrics.profit_factor < 0.5:
            risk_factors.append("Critical profit factor (<0.5)")
            risk_score += 25
        elif metrics.profit_factor < 1.0:
            risk_factors.append("Unprofitable (PF < 1.0)")
            risk_score += 15
        
        # Expectancy risk
        if metrics.expectancy < 0:
            risk_factors.append("Negative expectancy")
            risk_score += 20
        
        # Trade frequency risk
        if metrics.total_trades > 100:
            risk_factors.append("High trade frequency (>100/week)")
            risk_score += 5
        
        # Determine risk level
        if risk_score >= 50:
            risk_level = "CRITICAL"
            action = "HALT TRADING - Review and reset"
        elif risk_score >= 30:
            risk_level = "HIGH"
            action = "Reduce position sizes and frequency"
        elif risk_score >= 15:
            risk_level = "MODERATE"
            action = "Monitor closely, maintain discipline"
        else:
            risk_level = "LOW"
            action = "Continue current approach"
        
        return {
            'risk_level': risk_level,
            'risk_score': risk_score,
            'risk_factors': risk_factors,
            'recommended_action': action
        }
    
    def _calculate_overall_score(
        self,
        metrics: PerformanceMetrics,
        checklist_results: Dict[str, Tuple[bool, str]]
    ) -> float:
        """
        Calculate overall system score (0-100).
        
        Args:
            metrics: Performance metrics
            checklist_results: Checklist validation results
            
        Returns:
            Overall score (0-100)
        """
        score = 0
        
        # NO TRADE ratio score (0-25)
        no_trade_ratio = metrics.no_trade_ratio
        score += min(no_trade_ratio / self.min_no_trade_ratio, 1.0) * 25
        
        # A+ execution score (0-25)
        if metrics.total_trades > 0:
            a_plus_ratio = metrics.a_plus_executions / metrics.total_trades
            score += min(a_plus_ratio / 0.7, 1.0) * 25  # Target 70% A+
        else:
            score += 25  # No trades = perfect A+ ratio
        
        # Expected R score (0-20)
        expected_r = metrics.avg_expected_r
        score += min(expected_r / self.min_expected_r, 1.0) * 20
        
        # Profit factor score (0-15)
        profit_factor = metrics.profit_factor
        if profit_factor >= 2.0:
            score += 15
        elif profit_factor >= 1.5:
            score += 12
        elif profit_factor >= 1.0:
            score += 8
        elif profit_factor >= 0.5:
            score += 4
        else:
            score += 0
        
        # Win rate score (0-15)
        win_rate = metrics.win_rate
        if win_rate >= 0.5:
            score += 15
        elif win_rate >= 0.4:
            score += 12
        elif win_rate >= 0.3:
            score += 8
        elif win_rate >= 0.2:
            score += 4
        else:
            score += 0
        
        return min(score, 100)
    
    def _determine_status(
        self,
        overall_score: float,
        red_line_status: str
    ) -> str:
        """
        Determine overall system status.
        
        Args:
            overall_score: Calculated overall score
            red_line_status: Current red line status
            
        Returns:
            Status string
        """
        # Check red lines first
        if "SAFE MODE" in red_line_status:
            return "CRITICAL"
        elif "WARNING" in red_line_status:
            if overall_score >= 70:
                return "GOOD"
            else:
                return "WARNING"
        
        # Normal operation
        if overall_score >= 85:
            return "EXCELLENT"
        elif overall_score >= 70:
            return "GOOD"
        elif overall_score >= 50:
            return "WARNING"
        else:
            return "CRITICAL"
    
    def _checklist_passed(self, checklist_results: Dict[str, Tuple[bool, str]]) -> bool:
        """
        Check if all critical checklist items passed.
        
        Args:
            checklist_results: Checklist validation results
            
        Returns:
            True if all critical items passed
        """
        critical_items = ['no_trade_ratio', 'non_a_plus_executions', 'expected_r']
        
        for item in critical_items:
            if item in checklist_results:
                passed, _ = checklist_results[item]
                if not passed:
                    return False
        
        return True
    
    def _identify_top_pattern(self, reward_engine: RewardEngine) -> str:
        """
        Identify the most profitable pattern.
        
        Args:
            reward_engine: RewardEngine with trade history
            
        Returns:
            Pattern description string
        """
        recent_trades = reward_engine.trade_history[-50:]
        
        if not recent_trades:
            return "No data"
        
        # Group by execution quality
        quality_profits = {}
        for quality in ["A+", "A", "B", "C", "D"]:
            trades = [t for t in recent_trades if t.execution_quality == quality]
            if trades:
                quality_profits[quality] = {
                    'count': len(trades),
                    'total_profit': sum(t.profit_pct for t in trades),
                    'avg_profit': np.mean([t.profit_pct for t in trades])
                }
        
        # Find most profitable
        if quality_profits:
            top = max(quality_profits.items(), key=lambda x: x[1]['total_profit'])
            return f"{top[0]} trades (Avg: {top[1]['avg_profit']*100:.2f}%)"
        
        return "No profitable patterns"
    
    def get_safe_mode_status(self) -> Dict[str, Any]:
        """
        Get current safe mode status.
        
        Returns:
            Safe mode status dictionary
        """
        return {
            'consecutive_failures': self.consecutive_a_plus_failures,
            'threshold': self.consecutive_failures_for_safe_mode,
            'safe_mode_active': self.consecutive_a_plus_failures >= self.consecutive_failures_for_safe_mode,
            'last_review': self.last_review_date.isoformat() if self.last_review_date else None,
            'weekly_reports_count': len(self.weekly_reports)
        }
    
    def export_report(self, report: WeeklyReport) -> str:
        """
        Export report as JSON.
        
        Args:
            report: WeeklyReport to export
            
        Returns:
            JSON string representation
        """
        return json.dumps({
            'week_start': report.week_start.isoformat(),
            'week_end': report.week_end.isoformat(),
            'status': report.status,
            'overall_score': report.overall_score,
            'red_line_status': report.red_line_status,
            'metrics': report.metrics.to_dict(),
            'checklist_results': {
                k: {'passed': v[0], 'message': v[1]} 
                for k, v in report.checklist_results.items()
            },
            'recommendations': report.recommendations,
            'pattern_analysis': report.pattern_analysis,
            'risk_assessment': report.risk_assessment,
            'generated_at': report.generated_at.isoformat()
        }, indent=2)
