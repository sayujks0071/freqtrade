"""
Data Models for Matrix Agent Trading System
============================================
Core data structures and models for the trading system.

Author: Matrix Agent
Version: 1.0.0
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum
import json


class TradeDirection(Enum):
    """Trade direction enumeration."""
    LONG = "long"
    SHORT = "short"
    NEUTRAL = "neutral"


class TrendDirection(Enum):
    """Market trend direction."""
    UP = "up"
    DOWN = "down"
    RANGE = "range"
    UNKNOWN = "unknown"


class SignalSource(Enum):
    """Source of trading signal."""
    SFP = "sfp"
    MACRO = "macro"
    CONSENSUS = "consensus"
    REVERSAL = "reversal"
    NONE = "none"


class Decision(Enum):
    """Committee decision result."""
    APPROVE = "approve"
    REJECT = "reject"
    VETO = "veto"


class VetoReason(Enum):
    """Reasons for vetoing a trade."""
    MACRO_REJECTED = "macro_rejected"
    NO_SFP = "no_sfp"
    CONSENSUS_TOO_HIGH = "consensus_too_high"
    RISK_TOO_HIGH = "risk_too_high"
    EXPECTED_R_TOO_LOW = "expected_r_too_low"
    DRAWDOWN_LIMIT = "drawdown_limit"
    INVALID_CONFIGURATION = "invalid_configuration"


@dataclass
class PriceLevel:
    """Price level with metadata."""
    price: float
    timestamp: datetime
    volume: float = 0.0
    is_key_level: bool = False
    level_type: str = "support"  # support, resistance, liquidity
    
    
@dataclass
class SFPContext:
    """Swing Failure Pattern context and details."""
    pattern_type: str  # bullish_sfp, bearish_sfp
    entry_price: float
    stop_loss: float
    failure_point: float
    confirmation_price: float
    timeframe: str
    is_valid: bool = True
    invalidation_reason: Optional[str] = None
    liquidity_zone: Optional[float] = None
    risk_reward_ratio: float = 0.0
    
    
@dataclass
class MacroAnalysis:
    """Macro market analysis results."""
    trend: TrendDirection = TrendDirection.UNKNOWN
    rsi_4h: float = 50.0
    rsi_1d: float = 50.0
    funding_rate: float = 0.0
    price_position: str = "middle"  # edge, middle
    is_approved: bool = False
    approval_condition: Optional[str] = None
    rejection_reason: Optional[str] = None
    key_levels: List[PriceLevel] = field(default_factory=list)
    market_sentiment: str = "neutral"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'trend': self.trend.value,
            'rsi_4h': self.rsi_4h,
            'rsi_1d': self.rsi_1d,
            'funding_rate': self.funding_rate,
            'price_position': self.price_position,
            'is_approved': self.is_approved,
            'approval_condition': self.approval_condition,
            'rejection_reason': self.rejection_reason,
            'market_sentiment': self.market_sentiment
        }


@dataclass
class ConsensusAnalysis:
    """Market consensus analysis."""
    consensus_level: float = 0.0  # 0-100 scale
    funding_indicator: float = 0.0
    oi_indicator: float = 0.0
    sentiment_indicator: float = 0.0
    is_high_consensus: bool = False
    required_expected_r: float = 3.0
    can_trade: bool = True
    warning_reason: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'consensus_level': self.consensus_level,
            'funding_indicator': self.funding_indicator,
            'oi_indicator': self.oi_indicator,
            'sentiment_indicator': self.sentiment_indicator,
            'is_high_consensus': self.is_high_consensus,
            'required_expected_r': self.required_expected_r,
            'can_trade': self.can_trade,
            'warning_reason': self.warning_reason
        }


@dataclass
class RiskMetrics:
    """Risk management metrics."""
    account_balance: float = 1000.0
    available_balance: float = 1000.0
    max_position_size: float = 0.20  # 20% max position
    single_trade_risk: float = 0.01  # 1% max risk per trade
    max_drawdown_pct: float = 0.05  # 5% max drawdown
    current_drawdown: float = 0.0
    total_risk_exposure: float = 0.0
    open_positions_count: int = 0
    is_safe_mode: bool = False
    risk_warning: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'account_balance': self.account_balance,
            'available_balance': self.available_balance,
            'max_position_size': self.max_position_size,
            'single_trade_risk': self.single_trade_risk,
            'max_drawdown_pct': self.max_drawdown_pct,
            'current_drawdown': self.current_drawdown,
            'total_risk_exposure': self.total_risk_exposure,
            'open_positions_count': self.open_positions_count,
            'is_safe_mode': self.is_safe_mode,
            'risk_warning': self.risk_warning
        }


@dataclass
class TradeSignal:
    """Complete trade signal with all analysis data."""
    pair: str
    direction: TradeDirection
    entry_price: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    confidence: float = 0.0
    expected_r: float = 0.0
    source: SignalSource = SignalSource.NONE
    timeframe: str = "5m"
    timestamp: datetime = field(default_factory=datetime.now)
    
    # Analysis layers
    sfp_context: Optional[SFPContext] = None
    macro_analysis: Optional[MacroAnalysis] = None
    consensus_analysis: Optional[ConsensusAnalysis] = None
    risk_metrics: Optional[RiskMetrics] = None
    
    # Decision
    decision: Decision = Decision.REJECT
    veto_reason: Optional[VetoReason] = None
    rejection_reason: str = ""
    
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            'pair': self.pair,
            'direction': self.direction.value,
            'entry_price': self.entry_price,
            'stop_loss': self.stop_loss,
            'take_profit_1': self.take_profit_1,
            'take_profit_2': self.take_profit_2,
            'confidence': self.confidence,
            'expected_r': self.expected_r,
            'source': self.source.value,
            'timeframe': self.timeframe,
            'timestamp': self.timestamp.isoformat(),
            'decision': self.decision.value,
            'veto_reason': self.veto_reason.value if self.veto_reason else None,
            'rejection_reason': self.rejection_reason
        }
        
        if self.sfp_context:
            result['sfp_context'] = {
                'pattern_type': self.sfp_context.pattern_type,
                'entry_price': self.sfp_context.entry_price,
                'stop_loss': self.sfp_context.stop_loss,
                'failure_point': self.sfp_context.failure_point,
                'is_valid': self.sfp_context.is_valid,
                'risk_reward_ratio': self.sfp_context.risk_reward_ratio
            }
            
        if self.macro_analysis:
            result['macro_analysis'] = self.macro_analysis.to_dict()
            
        if self.consensus_analysis:
            result['consensus_analysis'] = self.consensus_analysis.to_dict()
            
        if self.risk_metrics:
            result['risk_metrics'] = self.risk_metrics.to_dict()
            
        return result
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)
    
    @property
    def risk_amount(self) -> float:
        """Calculate risk amount in quote currency."""
        return abs(self.entry_price - self.stop_loss) / self.entry_price
    
    @property
    def reward_amount(self) -> float:
        """Calculate potential reward."""
        if self.direction == TradeDirection.LONG:
            return (self.take_profit_1 - self.entry_price) / self.entry_price
        else:
            return (self.entry_price - self.take_profit_1) / self.entry_price
    
    @property
    def is_approved(self) -> bool:
        return self.decision == Decision.APPROVE


@dataclass
class MarketState:
    """Current market state snapshot."""
    pair: str
    current_price: float
    timestamp: datetime
    trend_4h: TrendDirection = TrendDirection.UNKNOWN
    trend_1d: TrendDirection = TrendDirection.UNKNOWN
    rsi_4h: float = 50.0
    rsi_1d: float = 50.0
    funding_rate: float = 0.0
    open_interest: float = 0.0
    volume_24h: float = 0.0
    volatility: float = 0.0
    key_levels: List[PriceLevel] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'pair': self.pair,
            'current_price': self.current_price,
            'timestamp': self.timestamp.isoformat(),
            'trend_4h': self.trend_4h.value,
            'trend_1d': self.trend_1d.value,
            'rsi_4h': self.rsi_4h,
            'rsi_1d': self.rsi_1d,
            'funding_rate': self.funding_rate,
            'open_interest': self.open_interest,
            'volume_24h': self.volume_24h,
            'volatility': self.volatility
        }


@dataclass
class CommitteeVote:
    """Individual committee member vote."""
    member_name: str
    vote: Decision
    confidence: float
    reasoning: str
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class CommitteeResult:
    """Committee decision result."""
    decision: Decision
    votes: List[CommitteeVote] = field(default_factory=list)
    final_reasoning: str = ""
    risk_score: float = 0.0
    expected_r_estimate: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'decision': self.decision.value,
            'votes': [
                {
                    'member': v.member_name,
                    'vote': v.vote.value,
                    'confidence': v.confidence,
                    'reasoning': v.reasoning
                }
                for v in self.votes
            ],
            'final_reasoning': self.final_reasoning,
            'risk_score': self.risk_score,
            'expected_r_estimate': self.expected_r_estimate,
            'timestamp': self.timestamp.isoformat()
        }


@dataclass 
class PerformanceMetrics:
    """Performance tracking metrics."""
    period_start: datetime
    period_end: datetime = field(default_factory=datetime.now)
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    total_return: float = 0.0
    max_drawdown: float = 0.0
    profit_factor: float = 0.0
    expectancy: float = 0.0
    average_trade_duration: float = 0.0
    no_trade_decisions: int = 0
    a_plus_executions: int = 0
    non_a_plus_executions: int = 0
    avg_expected_r: float = 0.0
    top_pattern: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'period_start': self.period_start.isoformat(),
            'period_end': self.period_end.isoformat(),
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'win_rate': self.win_rate,
            'total_return': self.total_return,
            'max_drawdown': self.max_drawdown,
            'profit_factor': self.profit_factor,
            'expectancy': self.expectancy,
            'average_trade_duration_minutes': self.average_trade_duration,
            'no_trade_decisions': self.no_trade_decisions,
            'a_plus_executions': self.a_plus_executions,
            'non_a_plus_executions': self.non_a_plus_executions,
            'avg_expected_r': self.avg_expected_r,
            'top_pattern': self.top_pattern
        }
    
    @property
    def no_trade_ratio(self) -> float:
        """Calculate ratio of no-trade decisions."""
        total = self.total_trades + self.no_trade_decisions
        if total == 0:
            return 0.0
        return self.no_trade_decisions / total
    
    @property
    def a_plus_ratio(self) -> float:
        """Calculate A+ execution ratio."""
        total = self.a_plus_executions + self.non_a_plus_executions
        if total == 0:
            return 0.0
        return self.a_plus_executions / total


@dataclass
class ExecutionResult:
    """Result of trade execution."""
    trade_id: str
    pair: str
    direction: TradeDirection
    status: str  # executed, rejected, failed, closed
    entry_price: Optional[float] = None
    exit_price: Optional[float] = None
    profit_pct: float = 0.0
    duration_minutes: float = 0.0
    execution_quality: str = "A+"  # A+, A, B, C, D
    mistakes: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'trade_id': self.trade_id,
            'pair': self.pair,
            'direction': self.direction.value,
            'status': self.status,
            'entry_price': self.entry_price,
            'exit_price': self.exit_price,
            'profit_pct': self.profit_pct,
            'duration_minutes': self.duration_minutes,
            'execution_quality': self.execution_quality,
            'mistakes': self.mistakes,
            'timestamp': self.timestamp.isoformat()
        }
