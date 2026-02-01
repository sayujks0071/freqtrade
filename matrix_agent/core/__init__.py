"""
Matrix Agent Crypto Trading System
===================================
A survivorship-focused trading system implementing the 8-layer architecture.

Core Principles:
- Survival > Profit
- Asymmetry > Win Rate
- NO TRADE is a successful decision
- Expected R < 3 → Mandatory NO TRADE
- No SFP → No trade allowed

System Architecture:
1. Macro Gatekeeper (Veto Layer)
2. Anti-Consensus Filter
3. Liquidity Hunter (SFP Hunter)
4. Committee Decision
5. Minimax Executor
6. Risk Governor
7. Reward Engine
8. Weekly Review Agent

Author: Matrix Agent
Version: 1.0.0
"""

from .matrix_agent import MatrixAgent
from .sfp_detector import SFPDetector
from .macro_gatekeeper import MacroGatekeeper
from .anti_consensus_filter import AntiConsensusFilter
from .risk_governor import RiskGovernor
from .committee_decision import CommitteeDecision
from .minimax_executor import MinimaxExecutor
from .reward_engine import RewardEngine
from .weekly_reviewer import WeeklyReviewer
from .data_provider import DataProvider
from .models import TradeSignal, MarketState, RiskMetrics

__all__ = [
    'MatrixAgent',
    'SFPDetector', 
    'MacroGatekeeper',
    'AntiConsensusFilter',
    'RiskGovernor',
    'CommitteeDecision',
    'MinimaxExecutor',
    'RewardEngine',
    'WeeklyReviewer',
    'DataProvider',
    'TradeSignal',
    'MarketState',
    'RiskMetrics'
]
