"""
Matrix Agent - Main Orchestrator
================================
Main entry point and orchestrator for the Matrix Agent trading system.

System Architecture:
1. Environment (Market)
2. Layer 1: Macro Gatekeeper (Veto Layer)
3. Layer 2: Anti-Consensus Filter
4. Layer 3: Liquidity Hunter (SFP Hunter)
5. Layer 4: Committee Decision
6. Layer 5: Minimax Executor
7. Layer 6: Risk Governor
8. Layer 7: Reward Engine (Post-trade)
9. Layer 8: Weekly Review Agent

Author: Matrix Agent
Version: 1.0.0
"""

import numpy as np
import pandas as pd
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta
import logging
import json

from .models import (
    TradeSignal, 
    MarketState, 
    Decision, 
    VetoReason,
    TradeDirection,
    SignalSource,
    RiskMetrics,
    CommitteeResult,
    ExecutionResult
)

from .sfp_detector import SFPDetector
from .macro_gatekeeper import MacroGatekeeper
from .anti_consensus_filter import AntiConsensusFilter
from .risk_governor import RiskGovernor
from .committee_decision import CommitteeDecision
from .minimax_executor import MinimaxExecutor
from .reward_engine import RewardEngine
from .weekly_reviewer import WeeklyReviewer
from .data_provider import DataProvider

logger = logging.getLogger(__name__)


class MatrixAgent:
    """
    Matrix Agent - Main Trading System Orchestrator
    
    Implements the complete 8-layer trading architecture:
    
    Core Principles:
    - Survival > Profit
    - Asymmetry > Win Rate
    - NO TRADE is a successful decision
    - Expected R < 3 → Mandatory NO TRADE
    - No SFP → No trade allowed
    
    Usage:
        agent = MatrixAgent()
        signal = agent.analyze_market("BTC/USDT")
        if signal.decision == Decision.APPROVE:
            result = agent.execute_trade(signal)
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize Matrix Agent.
        
        Args:
            config: Configuration dictionary with system parameters
        """
        self.config = config or self._default_config()
        
        # Initialize core components
        self.data_provider = DataProvider()
        self.sfp_detector = SFPDetector(self.config.get('sfp_config'))
        self.macro_gatekeeper = MacroGatekeeper(self.config.get('macro_config'))
        self.anti_consensus_filter = AntiConsensusFilter(self.config.get('consensus_config'))
        self.risk_governor = RiskGovernor(self.config.get('risk_config'))
        self.committee = CommitteeDecision(self.config.get('committee_config'))
        self.executor = MinimaxExecutor(self.config.get('executor_config'))
        self.reward_engine = RewardEngine(self.config.get('reward_config'))
        self.weekly_reviewer = WeeklyReviewer(self.config.get('reviewer_config'))
        
        # System state
        self.system_status = "RUNNING"
        self.safe_mode_active = False
        self.total_trades = 0
        self.successful_trades = 0
        self.rejected_trades = 0
        
        # Configure logging
        self._setup_logging()
        
        logger.info("Matrix Agent initialized")
        logger.info(f"System Status: {self.system_status}")
        logger.info(f"Safe Mode: {self.safe_mode_active}")
    
    def _default_config(self) -> Dict[str, Any]:
        """Return default configuration."""
        return {
            'sfp_config': {
                'swing_period': 5,
                'min_swing_strength': 0.5,
                'confirmation_bars': 1,
                'tolerance_pct': 0.001
            },
            'macro_config': {
                'rsi_bullish_low': 40,
                'rsi_bullish_high': 45,
                'rsi_bearish_low': 55,
                'rsi_bearish_high': 60,
                'extreme_funding_short': -0.0003,
                'extreme_funding_long': 0.0005
            },
            'consensus_config': {
                'high_consensus_threshold': 70,
                'base_required_rr': 3.0,
                'high_consensus_rr': 4.0
            },
            'risk_config': {
                'max_position_pct': 0.20,
                'single_trade_risk_pct': 0.01,
                'warning_drawdown_pct': 0.05,
                'critical_drawdown_pct': 0.08
            },
            'committee_config': {
                'macro_weight': 0.30,
                'risk_weight': 0.30,
                'liquidity_weight': 0.25,
                'consensus_weight': 0.15
            },
            'executor_config': {
                'base_expected_r_threshold': 3.0,
                'high_consensus_expected_r_threshold': 4.0,
                'max_risk_per_trade': 0.01
            },
            'reward_config': {
                'no_trade_reward': 1.0,
                'good_trade_reward': 0.5,
                'bad_trade_penalty': -1.0
            },
            'reviewer_config': {
                'min_no_trade_ratio': 0.60,
                'min_expected_r': 3.0,
                'max_non_a_plus': 2
            },
            'log_level': 'INFO',
            'trading_pairs': ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']
        }
    
    def _setup_logging(self):
        """Configure logging for the system."""
        log_level = getattr(logging, self.config.get('log_level', 'INFO'))
        
        # Create logs directory if needed
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler()
            ]
        )
    
    def analyze_market(self, pair: str) -> TradeSignal:
        """
        Analyze market and generate trade signal.
        
        Args:
            pair: Trading pair to analyze (e.g., 'BTC/USDT')
            
        Returns:
            TradeSignal with decision (APPROVE or REJECT)
        """
        logger.info(f"Analyzing market: {pair}")
        
        # Create empty signal
        signal = TradeSignal(
            pair=pair,
            direction=TradeDirection.NEUTRAL,
            entry_price=0,
            stop_loss=0,
            take_profit_1=0,
            take_profit_2=0,
            source=SignalSource.NONE
        )
        
        # Check safe mode
        if self.safe_mode_active:
            signal.decision = Decision.REJECT
            signal.rejection_reason = "System in safe mode"
            signal.veto_reason = VetoReason.INVALID_CONFIGURATION
            self.rejected_trades += 1
            return signal
        
        # Layer 1: Get market data
        try:
            market_state = self.data_provider.get_market_state(
                pair,
                funding_rate=self.data_provider.get_funding_rate(pair),
                open_interest=self.data_provider.get_open_interest(pair)
            )
        except Exception as e:
            logger.error(f"Error fetching market data: {e}")
            signal.decision = Decision.REJECT
            signal.rejection_reason = f"Data error: {str(e)}"
            signal.veto_reason = VetoReason.INVALID_CONFIGURATION
            self.rejected_trades += 1
            return signal
        
        # Layer 2: SFP Detection (Critical - must have SFP for trade)
        data_5m = self.data_provider.fetch_ohlcv(pair, "5m")
        sfp_context = self.sfp_detector.detect_sfp(data_5m, pair, "5m")
        
        if sfp_context is None:
            logger.info(f"No SFP detected for {pair}")
            signal.decision = Decision.REJECT
            signal.rejection_reason = "No SFP pattern detected"
            signal.veto_reason = VetoReason.NO_SFP
            self.rejected_trades += 1
            
            # Reward the NO TRADE decision
            self.reward_engine.evaluate_no_trade(signal)
            return signal
        
        signal.sfp_context = sfp_context
        signal.source = SignalSource.SFP
        
        # Set direction from SFP
        if sfp_context.pattern_type == 'bullish_sfp':
            signal.direction = TradeDirection.LONG
        else:
            signal.direction = TradeDirection.SHORT
        
        # Layer 3: Macro Gatekeeper
        macro_analysis = self.macro_gatekeeper.analyze(market_state)
        signal.macro_analysis = macro_analysis
        
        if not macro_analysis.is_approved:
            logger.info(f"Macro rejected {pair}: {macro_analysis.rejection_reason}")
            signal.decision = Decision.REJECT
            signal.rejection_reason = macro_analysis.rejection_reason
            signal.veto_reason = VetoReason.MACRO_REJECTED
            self.rejected_trades += 1
            self.reward_engine.evaluate_no_trade(signal)
            return signal
        
        # Layer 4: Anti-Consensus Filter
        consensus_analysis = self.anti_consensus_filter.analyze(market_state)
        signal.consensus_analysis = consensus_analysis
        
        if not consensus_analysis.can_trade:
            logger.info(f"Consensus rejected {pair}: {consensus_analysis.warning_reason}")
            signal.decision = Decision.REJECT
            signal.rejection_reason = consensus_analysis.warning_reason
            signal.veto_reason = VetoReason.CONSENSUS_TOO_HIGH
            self.rejected_trades += 1
            self.reward_engine.evaluate_no_trade(signal)
            return signal
        
        # Layer 5: Calculate trade levels from SFP
        signal.entry_price = sfp_context.entry_price
        signal.stop_loss = sfp_context.stop_loss
        signal.take_profit_1 = sfp_context.entry_price + (sfp_context.entry_price - sfp_context.stop_loss) * 2
        signal.take_profit_2 = sfp_context.entry_price + (sfp_context.entry_price - sfp_context.stop_loss) * 3
        
        if signal.direction == TradeDirection.SHORT:
            signal.take_profit_1 = sfp_context.entry_price - (sfp_context.stop_loss - sfp_context.entry_price) * 2
            signal.take_profit_2 = sfp_context.entry_price - (sfp_context.stop_loss - sfp_context.entry_price) * 3
        
        # Calculate expected R
        risk = abs(signal.entry_price - signal.stop_loss) / signal.entry_price
        reward = abs(signal.take_profit_1 - signal.entry_price) / signal.entry_price
        signal.expected_r = reward / risk if risk > 0 else 0
        
        # Layer 6: Risk Analysis
        risk_metrics = self.risk_governor.analyze_risk(signal)
        signal.risk_metrics = risk_metrics
        
        if not risk_metrics[1]:  # Risk check failed
            logger.info(f"Risk rejected {pair}: {risk_metrics[2]}")
            signal.decision = Decision.REJECT
            signal.rejection_reason = risk_metrics[2]
            signal.veto_reason = VetoReason.RISK_TOO_HIGH
            self.rejected_trades += 1
            self.reward_engine.evaluate_no_trade(signal)
            return signal
        
        # Layer 7: Committee Decision
        committee_result = self.committee.evaluate(signal)
        
        # Update signal with committee result
        if committee_result.decision == Decision.APPROVE:
            signal.decision = Decision.APPROVE
            signal.confidence = committee_result.expected_r_estimate / 5.0  # Normalize to 0-1
        else:
            signal.decision = Decision.REJECT
            signal.rejection_reason = committee_result.final_reasoning
            signal.veto_reason = VetoReason.INVALID_CONFIGURATION
            self.rejected_trades += 1
            self.reward_engine.evaluate_no_trade(signal)
            return signal
        
        # Validate Expected R threshold
        expected_r_threshold = self.executor._get_expected_r_threshold(signal)
        if signal.expected_r < expected_r_threshold:
            signal.decision = Decision.REJECT
            signal.rejection_reason = f"Expected R {signal.expected_r:.2f} < threshold {expected_r_threshold:.2f}"
            signal.veto_reason = VetoReason.EXPECTED_R_TOO_LOW
            self.rejected_trades += 1
            self.reward_engine.evaluate_no_trade(signal)
            return signal
        
        # Log approved signal
        logger.info(f"TRADE APPROVED: {pair} {signal.direction.value}")
        logger.info(f"  Entry: {signal.entry_price:.4f}")
        logger.info(f"  Stop: {signal.stop_loss:.4f}")
        logger.info(f"  TP1: {signal.take_profit_1:.4f}")
        logger.info(f"  Expected R: {signal.expected_r:.2f}")
        logger.info(f"  Confidence: {signal.confidence:.2f}")
        
        return signal
    
    def execute_trade(self, signal: TradeSignal) -> ExecutionResult:
        """
        Execute approved trade signal.
        
        Args:
            signal: Approved TradeSignal
            
        Returns:
            ExecutionResult
        """
        if signal.decision != Decision.APPROVE:
            logger.warning(f"Cannot execute rejected signal: {signal.rejection_reason}")
            return ExecutionResult(
                trade_id="rejected",
                pair=signal.pair,
                direction=signal.direction,
                status="rejected",
                mistakes=[signal.rejection_reason]
            )
        
        # Execute through Minimax Executor
        result, success = self.executor.execute(signal)
        
        if success:
            self.total_trades += 1
            logger.info(f"Trade executed: {signal.pair} {signal.direction.value} @ {result.entry_price}")
        else:
            logger.warning(f"Execution failed: {result.mistakes}")
        
        return result
    
    def analyze_and_execute(self, pair: str) -> Tuple[TradeSignal, ExecutionResult]:
        """
        Complete analyze and execute workflow.
        
        Args:
            pair: Trading pair to analyze
            
        Returns:
            Tuple of (TradeSignal, ExecutionResult)
        """
        # Analyze market
        signal = self.analyze_market(pair)
        
        # Execute if approved
        if signal.decision == Decision.APPROVE:
            result = self.execute_trade(signal)
            return signal, result
        else:
            # Return rejected execution result
            return signal, ExecutionResult(
                trade_id="notrade",
                pair=pair,
                direction=signal.direction,
                status="notrade",
                mistakes=[signal.rejection_reason]
            )
    
    def run_weekly_review(self) -> Any:
        """
        Run weekly performance review.
        
        Returns:
            WeeklyReport with findings
        """
        report = self.weekly_reviewer.run_weekly_review(self.reward_engine)
        
        # Check safe mode conditions
        safe_status = self.weekly_reviewer.get_safe_mode_status()
        
        if safe_status['safe_mode_active']:
            self.safe_mode_active = True
            self.system_status = "SAFE_MODE"
            logger.warning("SAFE MODE ACTIVATED - Consecutive weekly failures")
        
        return report
    
    def get_system_status(self) -> Dict[str, Any]:
        """
        Get current system status.
        
        Returns:
            Status dictionary
        """
        # Get health from reward engine
        health = self.reward_engine.get_system_health()
        
        # Get safe mode status
        safe_status = self.weekly_reviewer.get_safe_mode_status()
        
        return {
            'system_status': self.system_status,
            'safe_mode_active': self.safe_mode_active,
            'total_trades': self.total_trades,
            'rejected_trades': self.rejected_trades,
            'acceptance_rate': self.total_trades / (self.total_trades + self.rejected_trades) if (self.total_trades + self.rejected_trades) > 0 else 0,
            'health': health,
            'safe_mode_status': safe_status,
            'timestamp': datetime.now().isoformat()
        }
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """
        Get performance metrics.
        
        Returns:
            Performance metrics dictionary
        """
        metrics = self.reward_engine.calculate_performance_metrics()
        
        return {
            'total_trades': metrics.total_trades,
            'winning_trades': metrics.winning_trades,
            'losing_trades': metrics.losing_trades,
            'win_rate': metrics.win_rate,
            'total_return': metrics.total_return,
            'profit_factor': metrics.profit_factor,
            'no_trade_ratio': metrics.no_trade_ratio,
            'a_plus_ratio': metrics.a_plus_ratio,
            'avg_expected_r': metrics.avg_expected_r,
            'avg_trade_duration': metrics.average_trade_duration
        }
    
    def batch_analyze(
        self,
        pairs: Optional[List[str]] = None,
        filter_approved: bool = True
    ) -> List[TradeSignal]:
        """
        Analyze multiple trading pairs.
        
        Args:
            pairs: List of pairs to analyze (default: config pairs)
            filter_approved: Only return approved signals
            
        Returns:
            List of TradeSignals
        """
        if pairs is None:
            pairs = self.config.get('trading_pairs', ['BTC/USDT'])
        
        signals = []
        for pair in pairs:
            try:
                signal = self.analyze_market(pair)
                if not filter_approved or signal.decision == Decision.APPROVE:
                    signals.append(signal)
            except Exception as e:
                logger.error(f"Error analyzing {pair}: {e}")
        
        # Sort by expected R (highest first)
        signals.sort(key=lambda x: x.expected_r, reverse=True)
        
        return signals
    
    def close(self):
        """Clean up resources."""
        logger.info("Matrix Agent shutting down")
        
        # Run final weekly review
        try:
            report = self.run_weekly_review()
            logger.info(f"Final weekly review: {report.status}")
        except Exception as e:
            logger.error(f"Error in final review: {e}")
        
        # Clear data cache
        self.data_provider.clear_cache()
        
        self.system_status = "SHUTDOWN"
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False
    
    def __repr__(self):
        return f"MatrixAgent(status={self.system_status}, trades={self.total_trades})"
