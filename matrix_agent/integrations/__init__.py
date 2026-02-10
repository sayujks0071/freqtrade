"""
Matrix Agent - FreqTrade Integration Module
============================================
Integration layer for connecting Matrix Agent with FreqTrade.

This module provides:
1. MatrixAgentStrategy - FreqTrade strategy using Matrix Agent signals
2. Signal converter - Convert Matrix Agent signals to FreqTrade format
3. Webhook handler - Receive trade updates from FreqTrade

Author: Matrix Agent
Version: 1.0.0
"""

from .matrix_strategy import MatrixAgentStrategy
from .signal_converter import SignalConverter
from .webhook_handler import MatrixWebhookHandler

__all__ = [
    'MatrixAgentStrategy',
    'SignalConverter',
    'MatrixWebhookHandler'
]
