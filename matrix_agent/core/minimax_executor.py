"""
Minimax Executor - Game Theory Trade Execution
===============================================
Layer 5 of the Matrix Agent system.

Game Theory Execution:
1. Worst Case: Maximum I can lose?
2. Best Case: Maximum I can gain?

Execution Conditions:
- Expected R ≥ 3 (high consensus ≥ 4)
- Stop Loss = Outside SFP extreme
- Risk ≤ 1% of account

Author: Matrix Agent
Version: 1.0.0
"""

import numpy as np
import pandas as pd
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
import uuid

from .models import (
    TradeSignal, 
    TradeDirection, 
    Decision,
    VetoReason,
    ExecutionResult,
    RiskMetrics,
    SFPContext,
    CommitteeResult
)

logger = logging.getLogger(__name__)


class MinimaxExecutor:
    """
    Minimax Executor - Game Theory Trade Execution
    
    Executes approved trades with optimal risk/reward management:
    - Calculates worst-case and best-case scenarios
    - Ensures Expected R meets threshold
    - Manages position sizing and entry timing
    - Validates execution quality
    
    Philosophy:
    "Answer two questions: Worst Case? Best Case?"
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize Minimax Executor.
        
        Args:
            config: Configuration dictionary with execution parameters
        """
        self.config = config or self._default_config()
        
        # Expected R thresholds
        self.base_expected_r_threshold = self.config.get('base_expected_r_threshold', 3.0)
        self.high_consensus_expected_r_threshold = self.config.get('high_consensus_expected_r_threshold', 4.0)
        
        # Risk management
        self.max_risk_per_trade = self.config.get('max_risk_per_trade', 0.01)  # 1%
        self.max_position_pct = self.config.get('max_position_pct', 0.20)  # 20%
        
        # Execution quality thresholds
        self.execution_quality_thresholds = self.config.get('execution_quality_thresholds', {
            'A_plus': 0.95,  # Within 5% of ideal
            'A': 0.90,       # Within 10% of ideal
            'B': 0.80,       # Within 20% of ideal
            'C': 0.70,       # Within 30% of ideal
            'D': 0.50        # Worst case
        })
        
        # Slippage settings
        self.max_slippage_pct = self.config.get('max_slippage_pct', 0.005)  # 0.5%
        self.limit_order_offset = self.config.get('limit_order_offset', 0.001)  # 0.1%
        
    def _default_config(self) -> Dict[str, Any]:
        """Return default configuration."""
        return {
            'base_expected_r_threshold': 3.0,
            'high_consensus_expected_r_threshold': 4.0,
            'max_risk_per_trade': 0.01,       # 1% max risk
            'max_position_pct': 0.20,          # 20% max position
            'max_slippage_pct': 0.005,         # 0.5% max slippage
            'limit_order_offset': 0.001,       # 0.1% limit offset
            'execution_quality_thresholds': {
                'A_plus': 0.95,
                'A': 0.90,
                'B': 0.80,
                'C': 0.70,
                'D': 0.50
            },
            'use_limit_orders': True,
            'partial_tp_enabled': True,
            'partial_tp_level': 0.5,  # Take partial profit at 50% of target
            'trailing_stop_enabled': True,
            'trailing_stop_offset': 0.02  # 2% trailing stop
        }
    
    def execute(self, signal: TradeSignal) -> Tuple[ExecutionResult, bool]:
        """
        Execute trade signal with minimax strategy.
        
        Args:
            signal: Approved trade signal
            
        Returns:
            Tuple of (ExecutionResult, execution_successful)
        """
        trade_id = str(uuid.uuid4())[:8]
        
        # Validate signal
        if signal.decision != Decision.APPROVE:
            return ExecutionResult(
                trade_id=trade_id,
                pair=signal.pair,
                direction=signal.direction,
                status="rejected",
                execution_quality="N/A",
                mistakes=[f"Signal not approved: {signal.rejection_reason}"]
            ), False
        
        # Validate Expected R
        expected_r_threshold = self._get_expected_r_threshold(signal)
        if signal.expected_r < expected_r_threshold:
            return ExecutionResult(
                trade_id=trade_id,
                pair=signal.pair,
                direction=signal.direction,
                status="rejected",
                execution_quality="N/A",
                mistakes=[f"Expected R {signal.expected_r:.2f} < threshold {expected_r_threshold:.2f}"]
            ), False
        
        # Calculate worst case (loss scenario)
        worst_case_loss = self._calculate_worst_case(signal)
        
        # Validate worst case doesn't exceed limits
        if worst_case_loss > self.max_risk_per_trade:
            return ExecutionResult(
                trade_id=trade_id,
                pair=signal.pair,
                direction=signal.direction,
                status="rejected",
                execution_quality="N/A",
                mistakes=[f"Risk {worst_case_loss*100:.2f}% exceeds 1% limit"]
            ), False
        
        # Calculate best case (profit scenario)
        best_case_gain = self._calculate_best_case(signal)
        
        # Calculate position size
        position_size = self._calculate_position_size(signal, worst_case_loss)
        
        # Determine entry strategy
        entry_strategy = self._determine_entry_strategy(signal)
        
        # Calculate execution quality score
        execution_quality = self._calculate_execution_quality(signal, entry_strategy)
        
        # Build execution plan
        execution_plan = self._build_execution_plan(
            signal, position_size, entry_strategy
        )
        
        logger.info(f"Trade execution plan: {signal.pair} {signal.direction.value}")
        logger.info(f"  Entry: {execution_plan['entry_price']:.4f}")
        logger.info(f"  Stop: {execution_plan['stop_loss']:.4f}")
        logger.info(f"  TP1: {execution_plan['take_profit_1']:.4f}")
        logger.info(f"  TP2: {execution_plan['take_profit_2']:.4f}")
        logger.info(f"  Expected R: {signal.expected_r:.2f}")
        logger.info(f"  Position: {position_size:.4f}")
        
        # Return execution result (simulated execution)
        result = ExecutionResult(
            trade_id=trade_id,
            pair=signal.pair,
            direction=signal.direction,
            status="executed",
            entry_price=execution_plan['entry_price'],
            execution_quality=execution_quality,
            timestamp=datetime.now()
        )
        
        return result, True
    
    def _get_expected_r_threshold(self, signal: TradeSignal) -> float:
        """
        Get Expected R threshold based on consensus level.
        
        Args:
            signal: Trade signal with consensus analysis
            
        Returns:
            Expected R threshold
        """
        if signal.consensus_analysis and signal.consensus_analysis.is_high_consensus:
            return self.high_consensus_expected_r_threshold
        return self.base_expected_r_threshold
    
    def _calculate_worst_case(self, signal: TradeSignal) -> float:
        """
        Calculate worst-case loss percentage.
        
        Args:
            signal: Trade signal
            
        Returns:
            Maximum loss percentage
        """
        if signal.direction == TradeDirection.LONG:
            return abs(signal.entry_price - signal.stop_loss) / signal.entry_price
        else:
            return abs(signal.stop_loss - signal.entry_price) / signal.entry_price
    
    def _calculate_best_case(self, signal: TradeSignal) -> float:
        """
        Calculate best-case gain percentage.
        
        Args:
            signal: Trade signal
            
        Returns:
            Maximum gain percentage
        """
        if signal.direction == TradeDirection.LONG:
            return abs(signal.take_profit_1 - signal.entry_price) / signal.entry_price
        else:
            return abs(signal.entry_price - signal.take_profit_1) / signal.entry_price
    
    def _calculate_position_size(
        self,
        signal: TradeSignal,
        risk_pct: float
    ) -> float:
        """
        Calculate position size based on risk parameters.
        
        Args:
            signal: Trade signal
            risk_pct: Risk percentage to use
            
        Returns:
            Position size in base currency
        """
        # Use signal's risk metrics if available
        if signal.risk_metrics:
            account_balance = signal.risk_metrics.account_balance
        else:
            account_balance = 10000  # Default for calculation
        
        # Calculate position value based on risk
        risk_amount = account_balance * min(risk_pct, self.max_risk_per_trade)
        
        # Calculate position size
        if signal.direction == TradeDirection.LONG:
            position_value = risk_amount / risk_pct
        else:
            position_value = risk_amount / risk_pct
        
        # Apply max position limit
        max_position_value = account_balance * self.max_position_pct
        position_value = min(position_value, max_position_value)
        
        return position_value / signal.entry_price
    
    def _determine_entry_strategy(self, signal: TradeSignal) -> Dict[str, Any]:
        """
        Determine optimal entry strategy based on signal.
        
        Args:
            signal: Trade signal
            
        Returns:
            Entry strategy dictionary
        """
        strategy = {
            'use_limit': self.config.get('use_limit_orders', True),
            'limit_offset': self.config.get('limit_order_offset', 0.001),
            'market_if_not_filled': True,
            'reentry_attempts': 3
        }
        
        # For SFP entries, use limit orders with small offset
        if signal.sfp_context:
            if signal.direction == TradeDirection.LONG:
                # For long, place limit slightly below entry
                strategy['limit_price'] = signal.entry_price * (1 - strategy['limit_offset'])
            else:
                # For short, place limit slightly above entry
                strategy['limit_price'] = signal.entry_price * (1 + strategy['limit_offset'])
            
            strategy['entry_price'] = signal.entry_price
        
        return strategy
    
    def _calculate_execution_quality(
        self,
        signal: TradeSignal,
        entry_strategy: Dict[str, Any]
    ) -> str:
        """
        Calculate execution quality rating.
        
        Args:
            signal: Trade signal
            entry_strategy: Entry strategy used
            
        Returns:
            Quality rating (A+, A, B, C, D)
        """
        # Score based on various factors
        score = 1.0
        
        # Factor 1: Expected R quality
        if signal.expected_r >= 4:
            score *= 1.0
        elif signal.expected_r >= 3:
            score *= 0.95
        else:
            score *= 0.85
        
        # Factor 2: SFP quality
        if signal.sfp_context:
            if signal.sfp_context.risk_reward_ratio >= 3:
                score *= 1.0
            elif signal.sfp_context.risk_reward_ratio >= 2.5:
                score *= 0.95
            else:
                score *= 0.90
        
        # Factor 3: Committee consensus
        if signal.confidence >= 0.8:
            score *= 1.0
        elif signal.confidence >= 0.6:
            score *= 0.95
        else:
            score *= 0.85
        
        # Factor 4: Macro confirmation
        if signal.macro_analysis and signal.macro_analysis.is_approved:
            score *= 1.0
        else:
            score *= 0.90
        
        # Convert score to quality rating
        thresholds = self.execution_quality_thresholds
        
        if score >= thresholds['A_plus']:
            return "A+"
        elif score >= thresholds['A']:
            return "A"
        elif score >= thresholds['B']:
            return "B"
        elif score >= thresholds['C']:
            return "C"
        else:
            return "D"
    
    def _build_execution_plan(
        self,
        signal: TradeSignal,
        position_size: float,
        entry_strategy: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Build complete execution plan.
        
        Args:
            signal: Trade signal
            position_size: Calculated position size
            entry_strategy: Entry strategy
            
        Returns:
            Execution plan dictionary
        """
        # Calculate stop distance
        if signal.direction == TradeDirection.LONG:
            stop_distance = signal.entry_price - signal.stop_loss
            tp_distance = signal.take_profit_1 - signal.entry_price
        else:
            stop_distance = signal.stop_loss - signal.entry_price
            tp_distance = signal.entry_price - signal.take_profit_1
        
        # Calculate position value
        position_value = position_size * signal.entry_price
        
        # Build plan
        plan = {
            'pair': signal.pair,
            'direction': signal.direction.value,
            'position_size': position_size,
            'position_value': position_value,
            'entry_price': signal.entry_price,
            'stop_loss': signal.stop_loss,
            'take_profit_1': signal.take_profit_1,
            'take_profit_2': signal.take_profit_2,
            'risk_reward_ratio': signal.expected_r,
            'stop_distance_pct': (stop_distance / signal.entry_price) * 100,
            'tp_distance_pct': (tp_distance / signal.entry_price) * 100,
            'entry_strategy': entry_strategy,
            'partial_tp_enabled': self.config.get('partial_tp_enabled', True),
            'partial_tp_level': self.config.get('partial_tp_level', 0.5),
            'trailing_stop_enabled': self.config.get('trailing_stop_enabled', True),
            'trailing_stop_offset': self.config.get('trailing_stop_offset', 0.02),
            'timestamp': datetime.now().isoformat()
        }
        
        return plan
    
    def simulate_execution(
        self,
        signal: TradeSignal,
        market_data: pd.DataFrame
    ) -> Dict[str, Any]:
        """
        Simulate trade execution for backtesting.
        
        Args:
            signal: Trade signal
            market_data: Historical market data for simulation
            
        Returns:
            Simulation results dictionary
        """
        results = {
            'signal': signal.to_dict(),
            'execution': {},
            'outcome': 'pending',
            'profit_pct': 0.0,
            'duration_minutes': 0,
            'exit_reason': None,
            'mistakes': []
        }
        
        # Find entry bar
        entry_idx = None
        for i in range(len(market_data)):
            if signal.direction == TradeDirection.LONG:
                if market_data['low'].iloc[i] <= signal.entry_price:
                    entry_idx = i
                    break
            else:
                if market_data['high'].iloc[i] >= signal.entry_price:
                    entry_idx = i
                    break
        
        if entry_idx is None:
            results['outcome'] = 'no_entry'
            results['mistakes'].append('Entry price not reached')
            return results
        
        # Simulate from entry
        entry_price = signal.entry_price
        stop_price = signal.stop_loss
        tp1_price = signal.take_profit_1
        tp2_price = signal.take_profit_2
        
        partial_tp_filled = False
        exit_price = None
        exit_reason = None
        
        for i in range(entry_idx, len(market_data)):
            high = market_data['high'].iloc[i]
            low = market_data['low'].iloc[i]
            close = market_data['close'].iloc[i]
            
            # Check for stop loss hit
            if signal.direction == TradeDirection.LONG:
                if low <= stop_price:
                    exit_price = stop_price
                    exit_reason = 'stop_loss'
                    break
                # Check for take profit
                if not partial_tp_filled and high >= tp1_price:
                    # Partial TP filled
                    partial_tp_filled = True
                    results['execution']['partial_tp_filled'] = {
                        'price': tp1_price,
                        'bar': i - entry_idx
                    }
                if high >= tp2_price:
                    exit_price = tp2_price
                    exit_reason = 'take_profit_2'
                    break
            else:
                if high >= stop_price:
                    exit_price = stop_price
                    exit_reason = 'stop_loss'
                    break
                if not partial_tp_filled and low <= tp1_price:
                    partial_tp_filled = True
                    results['execution']['partial_tp_filled'] = {
                        'price': tp1_price,
                        'bar': i - entry_idx
                    }
                if low <= tp2_price:
                    exit_price = tp2_price
                    exit_reason = 'take_profit_2'
                    break
        
        if exit_price is None:
            # Use last close
            exit_price = market_data['close'].iloc[-1]
            exit_reason = 'timeout'
        
        # Calculate profit
        if signal.direction == TradeDirection.LONG:
            profit_pct = (exit_price - entry_price) / entry_price
        else:
            profit_pct = (entry_price - exit_price) / entry_price
        
        results['outcome'] = 'profitable' if profit_pct > 0 else 'losing'
        results['profit_pct'] = profit_pct
        results['duration_minutes'] = (entry_idx - entry_idx) * 5  # Assuming 5m timeframe
        results['exit_reason'] = exit_reason
        results['execution']['entry_bar'] = entry_idx
        results['execution']['exit_bar'] = entry_idx
        results['execution']['exit_price'] = exit_price
        
        return results
    
    def calculate_minimax_metrics(
        self,
        signal: TradeSignal
    ) -> Dict[str, Any]:
        """
        Calculate minimax (worst case / best case) metrics.
        
        Args:
            signal: Trade signal
            
        Returns:
            Minimax metrics dictionary
        """
        worst_case_loss = self._calculate_worst_case(signal)
        best_case_gain = self._calculate_best_case(signal)
        
        # Calculate asymmetry ratio
        asymmetry = best_case_gain / worst_case_loss if worst_case_loss > 0 else 0
        
        return {
'worst_case_loss_pct': worst_case_loss * 100,
            'best_case_gain_pct': best_case_gain * 100,
            'asymmetry_ratio': asymmetry,
            'expected_r': signal.expected_r,
            'kelly_fraction': self._calculate_kelly(signal),
            'edge': best_case_gain - worst_case_loss,
            'decision': 'TRADE' if asymmetry >= 3 else 'NO TRADE'
        }
    
    def _calculate_kelly(self, signal: TradeSignal) -> float:
        """
        Calculate Kelly Criterion for position sizing.
        
        Args:
            signal: Trade signal
            
        Returns:
            Kelly fraction (capped)
        """
        # Simplified Kelly calculation
        win_prob = 0.4  # Conservative estimate
        win_ratio = signal.expected_r
        
        kelly = win_prob - ((1 - win_prob) / win_ratio)
        
        # Apply half-Kelly for safety
        half_kelly = max(0, kelly * 0.5)
        
        # Cap at reasonable levels
        return min(half_kelly, 0.25)  # Max 25% Kelly
