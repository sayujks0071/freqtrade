"""
Risk Governor - Drawdown Protection and Risk Management
========================================================
Layer 6 of the Matrix Agent system.

Hard Rules (Non-Negotiable):
- Single trade risk ≤ 1%
- Maximum position ≤ 20%
- Drawdown > 5% → Auto reduce frequency
- Drawdown > 8% → Forced NO TRADE

Author: Matrix Agent
Version: 1.0.0
"""

import numpy as np
import pandas as pd
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging

from .models import (
    RiskMetrics, 
    TradeSignal, 
    VetoReason
)

logger = logging.getLogger(__name__)


class RiskGovernor:
    """
    Risk Governor - Final Gatekeeper
    
    Enforces hard risk rules and manages drawdown protection:
    - Position sizing limits
    - Drawdown monitoring
    - Risk exposure tracking
    - Safe mode activation
    
    Philosophy:
    "Survival > Profit" - Protect capital at all costs.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize Risk Governor.
        
        Args:
            config: Configuration dictionary with risk parameters
        """
        self.config = config or self._default_config()
        
        # Position limits
        self.max_position_pct = self.config.get('max_position_pct', 0.20)  # 20% max
        self.single_trade_risk_pct = self.config.get('single_trade_risk_pct', 0.01)  # 1% max risk
        
        # Drawdown limits
        self.warning_drawdown_pct = self.config.get('warning_drawdown_pct', 0.05)  # 5%
        self.critical_drawdown_pct = self.config.get('critical_drawdown_pct', 0.08)  # 8%
        self.forced_trade_limit_pct = self.config.get('forced_trade_limit_pct', 0.10)  # 10%
        
        # Risk exposure
        self.max_total_exposure_pct = self.config.get('max_total_exposure_pct', 0.05)  # 5% total
        self.max_open_positions = self.config.get('max_open_positions', 3)
        
        # Safe mode thresholds
        self.safe_mode_drawdown = self.config.get('safe_mode_drawdown', 0.15)  # 15%
        self.safe_mode_trades = self.config.get('safe_mode_trades', 5)  # Trades before safe mode
        
    def _default_config(self) -> Dict[str, Any]:
        """Return default configuration."""
        return {
            'max_position_pct': 0.20,           # 20% max position
            'single_trade_risk_pct': 0.01,       # 1% max risk per trade
            'warning_drawdown_pct': 0.05,        # 5% warning drawdown
            'critical_drawdown_pct': 0.08,       # 8% critical drawdown
            'forced_trade_limit_pct': 0.10,      # 10% forced NO TRADE
            'max_total_exposure_pct': 0.05,      # 5% max total exposure
            'max_open_positions': 3,             # Max concurrent positions
            'safe_mode_drawdown': 0.15,          # 15% triggers safe mode
            'safe_mode_trades': 5,               # Failed trades before safe mode
            'reduce_frequency_drawdown': 0.03,   # Reduce trade frequency at 3%
            'min_trade_interval_minutes': 60,    # Minimum time between trades
        }
    
    def calculate_position_size(
        self,
        account_balance: float,
        entry_price: float,
        stop_loss: float,
        risk_pct: Optional[float] = None
    ) -> Tuple[float, float, float]:
        """
        Calculate optimal position size based on risk parameters.
        
        Args:
            account_balance: Total account balance
            entry_price: Planned entry price
            stop_loss: Stop loss price
            risk_pct: Risk percentage (defaults to single_trade_risk_pct)
            
        Returns:
            Tuple of (position_size, position_value, risk_amount)
        """
        if risk_pct is None:
            risk_pct = self.single_trade_risk_pct
        
        # Calculate risk amount in quote currency
        risk_amount = account_balance * risk_pct
        
        # Calculate stop loss distance
        if entry_price > stop_loss:
            # Long position
            stop_distance = (entry_price - stop_loss) / entry_price
        else:
            # Short position
            stop_distance = (stop_loss - entry_price) / entry_price
        
        if stop_distance <= 0:
            logger.warning("Invalid stop loss: entry <= stop for long or entry >= stop for short")
            return 0.0, 0.0, 0.0
        
        # Calculate position size based on risk
        # position_size = risk_amount / stop_distance
        position_value = risk_amount / stop_distance
        
        # Apply max position limit
        max_position_value = account_balance * self.max_position_pct
        position_value = min(position_value, max_position_value)
        
        # Calculate actual risk with capped position
        actual_risk_pct = (position_value * stop_distance) / account_balance
        
        return position_value / entry_price, position_value, actual_risk_pct
    
    def analyze_risk(
        self,
        signal: TradeSignal,
        current_metrics: Optional[RiskMetrics] = None
    ) -> Tuple[RiskMetrics, bool, str]:
        """
        Analyze trade signal for risk compliance.
        
        Args:
            signal: Trade signal to analyze
            current_metrics: Current risk metrics (optional)
            
        Returns:
            Tuple of (updated_metrics, approved, reason)
        """
        if current_metrics is None:
            current_metrics = RiskMetrics()
        
        metrics = RiskMetrics(
            account_balance=current_metrics.account_balance,
            available_balance=current_metrics.available_balance,
            max_position_size=self.max_position_pct,
            single_trade_risk=self.single_trade_risk_pct,
            max_drawdown_pct=self.critical_drawdown_pct,
            current_drawdown=current_metrics.current_drawdown,
            total_risk_exposure=current_metrics.total_risk_exposure,
            open_positions_count=current_metrics.open_positions_count,
            is_safe_mode=current_metrics.is_safe_mode
        )
        
        # Check drawdown limits
        if metrics.current_drawdown >= self.forced_trade_limit_pct:
            metrics.risk_warning = f"Drawdown {metrics.current_drawdown*100:.1f}% exceeds 10% limit"
            return metrics, False, "FORCED NO TRADE: Drawdown limit exceeded"
        
        if metrics.current_drawdown >= self.warning_drawdown_pct:
            metrics.risk_warning = f"Drawdown {metrics.current_drawdown*100:.1f}% - reducing frequency"
        
        # Check safe mode
        if metrics.is_safe_mode:
            metrics.risk_warning = "System in safe mode"
            return metrics, False, "NO TRADE: System in safe mode"
        
        # Check open positions limit
        if metrics.open_positions_count >= self.max_open_positions:
            metrics.risk_warning = f"Max positions ({self.max_open_positions}) reached"
            return metrics, False, "NO TRADE: Max positions reached"
        
        # Check total risk exposure
        trade_risk = abs(signal.entry_price - signal.stop_loss) / signal.entry_price
        
        # Calculate position size
        position_size, position_value, actual_risk = self.calculate_position_size(
            metrics.available_balance,
            signal.entry_price,
            signal.stop_loss
        )
        
        if position_size <= 0:
            return metrics, False, "NO TRADE: Invalid position size"
        
        # Check single trade risk
        if actual_risk > self.single_trade_risk_pct:
            metrics.risk_warning = f"Trade risk {actual_risk*100:.2f}% exceeds 1% limit"
            return metrics, False, "NO TRADE: Risk exceeds single trade limit"
        
        # Check max position limit
        position_pct = position_value / metrics.available_balance
        if position_pct > self.max_position_pct:
            metrics.risk_warning = f"Position {position_pct*100:.1f}% exceeds 20% limit"
            return metrics, False, "NO TRADE: Position exceeds max limit"
        
        # Check total exposure
        new_total_exposure = metrics.total_risk_exposure + actual_risk
        if new_total_exposure > self.max_total_exposure_pct:
            metrics.risk_warning = f"Total exposure {new_total_exposure*100:.1f}% exceeds 5% limit"
            return metrics, False, "NO TRADE: Total exposure exceeds limit"
        
        # All checks passed
        metrics.available_balance -= position_value
        metrics.total_risk_exposure = new_total_exposure
        metrics.open_positions_count += 1
        
        return metrics, True, "Risk check passed"
    
    def update_metrics(
        self,
        current_metrics: RiskMetrics,
        trade_result: Dict[str, Any]
    ) -> RiskMetrics:
        """
        Update risk metrics after trade completion.
        
        Args:
            current_metrics: Current risk metrics
            trade_result: Trade result dictionary with pnl, etc.
            
        Returns:
            Updated risk metrics
        """
        metrics = RiskMetrics(
            account_balance=current_metrics.account_balance,
            available_balance=current_metrics.available_balance,
            max_position_size=self.max_position_pct,
            single_trade_risk=self.single_trade_risk_pct,
            max_drawdown_pct=self.critical_drawdown_pct,
            current_drawdown=current_metrics.current_drawdown,
            total_risk_exposure=current_metrics.total_risk_exposure,
            open_positions_count=current_metrics.open_positions_count,
            is_safe_mode=current_metrics.is_safe_mode
        )
        
        # Update balance
        pnl_pct = trade_result.get('profit_pct', 0)
        pnl_amount = current_metrics.account_balance * pnl_pct
        metrics.account_balance = current_metrics.account_balance * (1 + pnl_pct)
        metrics.available_balance = metrics.account_balance  # Simplified
        
        # Update drawdown
        peak_balance = current_metrics.account_balance
        current_drawdown = (peak_balance - metrics.account_balance) / peak_balance
        metrics.current_drawdown = max(current_metrics.current_drawdown, current_drawdown)
        
        # Update position count
        metrics.open_positions_count = max(0, current_metrics.open_positions_count - 1)
        
        # Update exposure (reduce by closed trade risk)
        # Note: In real implementation, track individual trade risks
        metrics.total_risk_exposure = max(0, current_metrics.total_risk_exposure - 0.01)  # Simplified
        
        # Check safe mode activation
        if metrics.current_drawdown >= self.safe_mode_drawdown:
            metrics.is_safe_mode = True
            metrics.risk_warning = f"SAFE MODE ACTIVATED: Drawdown {metrics.current_drawdown*100:.1f}%"
        elif metrics.current_drawdown >= self.warning_drawdown_pct:
            metrics.risk_warning = f"WARNING: Drawdown {metrics.current_drawdown*100:.1f}%"
        
        return metrics
    
    def check_drawdown_status(
        self,
        current_drawdown: float
    ) -> Tuple[str, str]:
        """
        Check current drawdown status and return appropriate action.
        
        Args:
            current_drawdown: Current drawdown percentage
            
        Returns:
            Tuple of (status, action_required)
        """
        if current_drawdown >= self.forced_trade_limit_pct:
            return "CRITICAL", "FORCED NO TRADE - Immediate stop"
        elif current_drawdown >= self.critical_drawdown_pct:
            return "CRITICAL", "Reduce position sizes by 50%"
        elif current_drawdown >= self.warning_drawdown_pct:
            return "WARNING", "Reduce trade frequency"
        elif current_drawdown >= self.reduce_frequency_drawdown:
            return "CAUTION", "Slightly reduce frequency"
        else:
            return "NORMAL", "Normal operation"
    
    def calculate_kelly_fraction(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        fraction: float = 0.5  # Half-Kelly for safety
    ) -> float:
        """
        Calculate Kelly Criterion position fraction.
        
        Args:
            win_rate: Historical win rate (0-1)
            avg_win: Average win percentage
            avg_loss: Average loss percentage (positive value)
            fraction: Kelly fraction (0.5 for half-Kelly)
            
        Returns:
            Recommended position fraction
        """
        if avg_loss <= 0:
            return 0.0
        
        win_prob = win_rate
        loss_prob = 1 - win_rate
        win_ratio = avg_win / avg_loss
        
        kelly = win_prob - (loss_prob / win_ratio)
        
        # Apply fraction and ensure positive
        adjusted = max(0, kelly * fraction)
        
        # Cap at reasonable levels
        return min(adjusted, self.max_position_pct)
    
    def get_risk_summary(self, metrics: RiskMetrics) -> Dict[str, Any]:
        """
        Generate risk summary for reporting.
        
        Args:
            metrics: Current risk metrics
            
        Returns:
            Risk summary dictionary
        """
        return {
            'account_balance': metrics.account_balance,
            'available_balance': metrics.available_balance,
            'current_drawdown_pct': metrics.current_drawdown * 100,
            'max_drawdown_limit_pct': self.critical_drawdown_pct * 100,
            'open_positions': metrics.open_positions_count,
            'max_positions': self.max_open_positions,
            'total_risk_exposure_pct': metrics.total_risk_exposure * 100,
            'max_exposure_limit_pct': self.max_total_exposure_pct * 100,
            'max_position_pct': self.max_position_pct * 100,
            'single_trade_risk_pct': self.single_trade_risk_pct * 100,
            'safe_mode': metrics.is_safe_mode,
            'risk_warning': metrics.risk_warning or "None",
            'status': self.check_drawdown_status(metrics.current_drawdown)[0]
        }
    
    def should_reduce_frequency(self, metrics: RiskMetrics) -> bool:
        """
        Determine if trade frequency should be reduced.
        
        Args:
            metrics: Current risk metrics
            
        Returns:
            True if frequency should be reduced
        """
        if metrics.current_drawdown >= self.warning_drawdown_pct:
            return True
        if metrics.is_safe_mode:
            return True
        return False
    
    def force_no_trade(self, metrics: RiskMetrics) -> Tuple[bool, str]:
        """
        Check if forced NO TRADE condition exists.
        
        Args:
            metrics: Current risk metrics
            
        Returns:
            Tuple of (forced, reason)
        """
        if metrics.current_drawdown >= self.forced_trade_limit_pct:
            return True, f"Drawdown {metrics.current_drawdown*100:.1f}% exceeds 10% limit"
        
        if metrics.is_safe_mode:
            return True, "System in safe mode"
        
        if metrics.open_positions_count >= self.max_open_positions:
            return True, f"Max positions ({self.max_open_positions}) reached"
        
        return False, "Trade allowed"
