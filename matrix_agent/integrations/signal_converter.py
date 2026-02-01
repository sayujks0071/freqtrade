"""
Signal Converter - Matrix Agent to FreqTrade Format
====================================================
Converts Matrix Agent signals to FreqTrade-compatible format.

This module handles:
1. Signal format conversion
2. Order parameter extraction
3. Trade metadata generation

Author: Matrix Agent
Version: 1.0.0
"""

import json
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import logging

from matrix_agent.core import TradeSignal, TradeDirection, Decision

logger = logging.getLogger(__name__)


@dataclass
class FreqTradeSignal:
    """FreqTrade-compatible signal format."""
    pair: str
    enter_long: bool
    enter_short: bool
    exit_long: bool
    exit_short: bool
    stop_loss: float
    take_profit: float
    trailing_stop: bool = False
    trailing_stop_offset: float = 0.02
    order_type: str = "limit"
    time_in_force: str = "GTC"
    stake_amount: Optional[float] = None
    leverage: int = 1
    custom_info: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'pair': self.pair,
            'enter_long': self.enter_long,
            'enter_short': self.enter_short,
            'exit_long': self.exit_long,
            'exit_short': self.exit_short,
            'stop_loss': self.stop_loss,
            'take_profit': self.take_profit,
            'trailing_stop': self.trailing_stop,
            'trailing_stop_offset': self.trailing_stop_offset,
            'order_type': self.order_type,
            'time_in_force': self.time_in_force,
            'stake_amount': self.stake_amount,
            'leverage': self.leverage,
            'custom_info': self.custom_info,
            'timestamp': self.timestamp.isoformat()
        }
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)


class SignalConverter:
    """
    Signal Converter - Matrix Agent to FreqTrade Format
    
    Converts Matrix Agent trade signals to FreqTrade-compatible format
    for seamless integration.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize signal converter.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config or {}
        
        # Default parameters
        self.default_stake_amount = self.config.get('stake_amount')
        self.default_leverage = self.config.get('leverage', 1)
        self.use_trailing_stop = self.config.get('use_trailing_stop', False)
        self.trailing_stop_offset = self.config.get('trailing_stop_offset', 0.02)
        
    def convert_signal(
        self,
        signal: TradeSignal,
        current_price: float,
        stake_amount: Optional[float] = None
    ) -> FreqTradeSignal:
        """
        Convert Matrix Agent signal to FreqTrade format.
        
        Args:
            signal: Matrix Agent TradeSignal
            current_price: Current market price
            stake_amount: Position size (optional)
            
        Returns:
            FreqTradeSignal
        """
        # Determine entry direction
        enter_long = signal.direction == TradeDirection.LONG
        enter_short = signal.direction == TradeDirection.SHORT
        
        # Calculate stop loss and take profit
        if signal.direction == TradeDirection.LONG:
            stop_loss = signal.stop_loss
            take_profit = signal.take_profit_1
        else:
            stop_loss = signal.stop_loss
            take_profit = signal.take_profit_1
        
        # Build custom info
        custom_info = {
            'matrix_agent': {
                'signal_id': signal.source.value,
                'expected_r': signal.expected_r,
                'confidence': signal.confidence,
                'sfp_type': signal.sfp_context.pattern_type if signal.sfp_context else None,
                'macro_approved': signal.macro_analysis.is_approved if signal.macro_analysis else False,
                'consensus_level': signal.consensus_analysis.consensus_level if signal.consensus_analysis else 0,
            },
            'original_signal': signal.to_dict()
        }
        
        # Create FreqTrade signal
        ft_signal = FreqTradeSignal(
            pair=signal.pair,
            enter_long=enter_long,
            enter_short=enter_short,
            exit_long=False,  # Exit managed by minimal_roi
            exit_short=False,
            stop_loss=stop_loss,
            take_profit=take_profit,
            trailing_stop=self.use_trailing_stop,
            trailing_stop_offset=self.trailing_stop_offset,
            stake_amount=stake_amount or self.default_stake_amount,
            leverage=self.default_leverage,
            custom_info=custom_info,
            timestamp=datetime.now()
        )
        
        return ft_signal
    
    def convert_rejection(
        self,
        signal: TradeSignal
    ) -> FreqTradeSignal:
        """
        Convert Matrix Agent rejection to signal.
        
        Args:
            signal: Rejected TradeSignal
            
        Returns:
            FreqTradeSignal with no entry
        """
        return FreqTradeSignal(
            pair=signal.pair,
            enter_long=False,
            enter_short=False,
            exit_long=False,
            exit_short=False,
            stop_loss=0,
            take_profit=0,
            custom_info={
                'matrix_agent': {
                    'rejected': True,
                    'reason': signal.rejection_reason,
                    'veto_reason': signal.veto_reason.value if signal.veto_reason else None
                }
            },
            timestamp=datetime.now()
        )
    
    def extract_order_params(
        self,
        signal: FreqTradeSignal,
        account_balance: float
    ) -> Dict[str, Any]:
        """
        Extract order parameters for FreqTrade.
        
        Args:
            signal: FreqTradeSignal
            account_balance: Total account balance
            
        Returns:
            Dictionary of order parameters
        """
        params = {
            'pair': signal.pair,
            'side': 'buy' if signal.enter_long else 'sell' if signal.enter_short else 'unknown',
            'ordertype': signal.order_type,
            'time_in_force': signal.time_in_force,
            'stoploss': self._calculate_stoploss_pct(signal.stop_loss, signal.pair),
            'take_profit': self._calculate_takeprofit_pct(signal.take_profit, signal.pair),
        }
        
        # Calculate stake amount
        if signal.stake_amount:
            params['stake_amount'] = signal.stake_amount
        else:
            # Use 20% of account by default
            params['stake_amount'] = account_balance * 0.20
        
        # Leverage
        params['leverage'] = signal.leverage
        
        # Trailing stop
        if signal.trailing_stop:
            params['trailing_stop'] = True
            params['trailing_stop_offset'] = signal.trailing_stop_offset
        
        return params
    
    def _calculate_stoploss_pct(
        self,
        stop_price: float,
        pair: str
    ) -> float:
        """
        Calculate stoploss percentage from absolute price.
        
        Args:
            stop_price: Stop loss price
            pair: Trading pair
            
        Returns:
            Stop loss percentage (e.g., -0.10 for 10% stop)
        """
        # In real implementation, use current market price
        # For now, calculate from pair-specific base price
        base_prices = {
            'BTC/USDT': 65000,
            'ETH/USDT': 3500,
            'SOL/USDT': 150
        }
        
        current_price = base_prices.get(pair, 1000)
        
        if current_price > 0:
            return (stop_price - current_price) / current_price
        return -0.10
    
    def _calculate_takeprofit_pct(
        self,
        tp_price: float,
        pair: str
    ) -> float:
        """
        Calculate take profit percentage from absolute price.
        
        Args:
            tp_price: Take profit price
            pair: Trading pair
            
        Returns:
            Take profit percentage (e.g., 0.03 for 3% profit)
        """
        base_prices = {
            'BTC/USDT': 65000,
            'ETH/USDT': 3500,
            'SOL/USDT': 150
        }
        
        current_price = base_prices.get(pair, 1000)
        
        if current_price > 0:
            return (tp_price - current_price) / current_price
        return 0.03
    
    def batch_convert(
        self,
        signals: list,
        current_prices: Dict[str, float]
    ) -> Dict[str, FreqTradeSignal]:
        """
        Convert multiple signals.
        
        Args:
            signals: List of TradeSignals
            current_prices: Dictionary of current prices by pair
            
        Returns:
            Dictionary of FreqTradeSignals by pair
        """
        result = {}
        
        for signal in signals:
            price = current_prices.get(signal.pair, 0)
            ft_signal = self.convert_signal(signal, price)
            result[signal.pair] = ft_signal
        
        return result
    
    def get_signal_summary(self, signal: FreqTradeSignal) -> str:
        """
        Generate human-readable signal summary.
        
        Args:
            signal: FreqTradeSignal
            
        Returns:
            Summary string
        """
        direction = "LONG" if signal.enter_long else "SHORT" if signal.enter_short else "NONE"
        
        summary = f"Signal: {signal.pair} {direction}\n"
        summary += f"  Entry: {'YES' if signal.enter_long or signal.enter_short else 'NO'}\n"
        summary += f"  Stop Loss: {signal.stop_loss:.4f}\n"
        summary += f"  Take Profit: {signal.take_profit:.4f}\n"
        
        if signal.custom_info.get('matrix_agent'):
            ma_info = signal.custom_info['matrix_agent']
            summary += f"  Expected R: {ma_info.get('expected_r', 0):.2f}\n"
            summary += f"  Confidence: {ma_info.get('confidence', 0):.2f}\n"
            summary += f"  SFP Type: {ma_info.get('sfp_type', 'None')}\n"
        
        return summary
    
    def validate_signal(self, signal: FreqTradeSignal) -> Tuple[bool, str]:
        """
        Validate FreqTrade signal.
        
        Args:
            signal: FreqTradeSignal to validate
            
        Returns:
            Tuple of (is_valid, reason)
        """
        # Check pair
        if not signal.pair or '/' not in signal.pair:
            return False, "Invalid pair format"
        
        # Check entry/exit consistency
        if signal.enter_long and signal.enter_short:
            return False, "Cannot be both long and short"
        
        # Check stop loss
        if signal.enter_long or signal.enter_short:
            if signal.stop_loss <= 0:
                return False, "Invalid stop loss price"
            if signal.take_profit <= 0:
                return False, "Invalid take profit price"
        
        # Check custom info
        if not signal.custom_info:
            return False, "Missing custom info"
        
        return True, "Valid signal"


@dataclass
class TradeMetadata:
    """Metadata for trade tracking."""
    trade_id: str
    pair: str
    signal_timestamp: datetime
    expected_r: float
    confidence: float
    sfp_type: str
    macro_approved: bool
    consensus_level: float
    execution_quality: str = "pending"
    exit_reason: Optional[str] = None
    profit_pct: float = 0.0
    actual_r: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'trade_id': self.trade_id,
            'pair': self.pair,
            'signal_timestamp': self.signal_timestamp.isoformat(),
            'expected_r': self.expected_r,
            'confidence': self.confidence,
            'sfp_type': self.sfp_type,
            'macro_approved': self.macro_approved,
            'consensus_level': self.consensus_level,
            'execution_quality': self.execution_quality,
            'exit_reason': self.exit_reason,
            'profit_pct': self.profit_pct,
            'actual_r': self.actual_r
        }


class MetadataTracker:
    """
    Trade Metadata Tracker
    
    Tracks trade metadata for performance analysis.
    """
    
    def __init__(self):
        """Initialize metadata tracker."""
        self.trades: Dict[str, TradeMetadata] = {}
        
    def add_trade(
        self,
        trade_id: str,
        signal: TradeSignal
    ) -> TradeMetadata:
        """
        Add trade metadata.
        
        Args:
            trade_id: Unique trade identifier
            signal: Original TradeSignal
            
        Returns:
            TradeMetadata
        """
        metadata = TradeMetadata(
            trade_id=trade_id,
            pair=signal.pair,
            signal_timestamp=datetime.now(),
            expected_r=signal.expected_r,
            confidence=signal.confidence,
            sfp_type=signal.sfp_context.pattern_type if signal.sfp_context else None,
            macro_approved=signal.macro_analysis.is_approved if signal.macro_analysis else False,
            consensus_level=signal.consensus_analysis.consensus_level if signal.consensus_analysis else 0
        )
        
        self.trades[trade_id] = metadata
        return metadata
    
    def update_trade(
        self,
        trade_id: str,
        execution_quality: Optional[str] = None,
        exit_reason: Optional[str] = None,
        profit_pct: Optional[float] = None,
        actual_r: Optional[float] = None
    ) -> Optional[TradeMetadata]:
        """
        Update trade metadata.
        
        Args:
            trade_id: Trade identifier
            execution_quality: Execution quality rating
            exit_reason: Reason for exit
            profit_pct: Profit percentage
            actual_r: Actual R achieved
            
        Returns:
            Updated TradeMetadata or None
        """
        if trade_id not in self.trades:
            return None
        
        metadata = self.trades[trade_id]
        
        if execution_quality:
            metadata.execution_quality = execution_quality
        if exit_reason:
            metadata.exit_reason = exit_reason
        if profit_pct is not None:
            metadata.profit_pct = profit_pct
        if actual_r is not None:
            metadata.actual_r = actual_r
        
        return metadata
    
    def get_trade(self, trade_id: str) -> Optional[TradeMetadata]:
        """Get trade metadata by ID."""
        return self.trades.get(trade_id)
    
    def get_all_trades(self) -> list:
        """Get all trades."""
        return list(self.trades.values())
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """
        Get performance summary from metadata.
        
        Returns:
            Performance summary dictionary
        """
        trades = list(self.trades.values())
        
        if not trades:
            return {'message': 'No trades recorded'}
        
        # Calculate metrics
        total = len(trades)
        completed = [t for t in trades if t.exit_reason]
        
        winning = [t for t in completed if t.profit_pct > 0]
        losing = [t for t in completed if t.profit_pct <= 0]
        
        win_rate = len(winning) / len(completed) if completed else 0
        avg_profit = sum(t.profit_pct for t in winning) / len(winning) if winning else 0
        avg_loss = sum(t.profit_pct for t in losing) / len(losing) if losing else 0
        
        avg_expected_r = sum(t.expected_r for t in trades) / total if total else 0
        avg_actual_r = sum(t.actual_r for t in completed) / len(completed) if completed else 0
        
        return {
            'total_trades': total,
            'completed_trades': len(completed),
            'winning_trades': len(winning),
            'losing_trades': len(losing),
            'win_rate': win_rate,
            'avg_profit': avg_profit,
            'avg_loss': avg_loss,
            'avg_expected_r': avg_expected_r,
            'avg_actual_r': avg_actual_r,
            'a_plus_executions': len([t for t in trades if t.execution_quality == 'A+']),
            'execution_quality_breakdown': {
                'A+': len([t for t in trades if t.execution_quality == 'A+']),
                'A': len([t for t in trades if t.execution_quality == 'A']),
                'B': len([t for t in trades if t.execution_quality == 'B']),
                'C': len([t for t in trades if t.execution_quality == 'C']),
                'D': len([t for t in trades if t.execution_quality == 'D']),
            }
        }
