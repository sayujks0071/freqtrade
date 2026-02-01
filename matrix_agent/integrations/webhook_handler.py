"""
Webhook Handler - Matrix Agent Trade Updates
=============================================
Handles trade updates from FreqTrade via webhooks.

This module:
1. Receives trade events from FreqTrade
2. Updates Matrix Agent tracking
3. Provides feedback to Reward Engine
4. Triggers weekly reviews

Author: Matrix Agent
Version: 1.0.0
"""

import json
import hmac
import hashlib
from typing import Optional, Dict, Any, List
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import logging
import uuid

from matrix_agent.core import (
    MatrixAgent,
    RewardEngine,
    TradeSignal,
    ExecutionResult,
    TradeDirection,
    Decision
)
from .signal_converter import MetadataTracker

logger = logging.getLogger(__name__)


class MatrixWebhookHandler(BaseHTTPRequestHandler):
    """
    HTTP Handler for FreqTrade Webhook Updates
    
    Receives trade events from FreqTrade and updates Matrix Agent.
    """
    
    def log_message(self, format, *args):
        """Override to use logger."""
        logger.info(f"Webhook: {format % args}")
    
    def do_GET(self):
        """Handle GET requests."""
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        
        response = {
            'status': 'ok',
            'message': 'Matrix Agent Webhook Handler',
            'endpoints': [
                'POST /webhook/entry - Trade entry notification',
                'POST /webhook/exit - Trade exit notification',
                'POST /webhook/status - Trade status update',
                'GET /health - Health check'
            ]
        }
        
        self.wfile.write(json.dumps(response, indent=2).encode())
    
    def do_POST(self):
        """Handle POST requests."""
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)
        
        try:
            data = json.loads(body.decode())
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
            return
        
        # Route to appropriate handler
        if '/entry' in self.path:
            self.handle_entry(data)
        elif '/exit' in self.path:
            self.handle_exit(data)
        elif '/status' in self.path:
            self.handle_status(data)
        else:
            self.send_error(404, "Unknown endpoint")
            return
    
    def handle_entry(self, data: dict):
        """Handle trade entry notification."""
        try:
            trade_id = data.get('trade_id', str(uuid.uuid4()))
            pair = data.get('pair')
            entry_price = data.get('entry_price')
            amount = data.get('amount')
            direction = data.get('direction', 'long')
            
            logger.info(f"Trade entry: {pair} {direction} @ {entry_price}")
            
            # Store in global tracker
            if hasattr(self, 'metadata_tracker'):
                self.metadata_tracker.add_trade(
                    trade_id,
                    TradeSignal(
                        pair=pair,
                        direction=TradeDirection.LONG if direction == 'long' else TradeDirection.SHORT,
                        entry_price=entry_price,
                        stop_loss=data.get('stop_loss', 0),
                        take_profit_1=data.get('take_profit', 0),
                        take_profit_2=0,
                        expected_r=data.get('expected_r', 0),
                        confidence=data.get('confidence', 0),
                        decision=Decision.APPROVE
                    )
                )
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            response = {
                'status': 'ok',
                'trade_id': trade_id,
                'message': 'Entry recorded'
            }
            
            self.wfile.write(json.dumps(response, indent=2).encode())
            
        except Exception as e:
            logger.error(f"Error handling entry: {e}")
            self.send_error(500, str(e))
    
    def handle_exit(self, data: dict):
        """Handle trade exit notification."""
        try:
            trade_id = data.get('trade_id')
            pair = data.get('pair')
            exit_price = data.get('exit_price')
            profit_pct = data.get('profit_pct', 0)
            exit_reason = data.get('exit_reason')
            
            logger.info(f"Trade exit: {pair} {profit_pct*100:.2f}% - {exit_reason}")
            
            # Update metadata tracker
            if hasattr(self, 'metadata_tracker') and trade_id:
                # Calculate actual R
                expected_r = 0
                if hasattr(self, 'matrix_agent'):
                    metrics = self.matrix_agent.reward_engine.calculate_performance_metrics()
                    expected_r = metrics.avg_expected_r
                
                actual_r = profit_pct / 0.01 if profit_pct != 0 else 0  # Assuming 1% risk
                
                self.metadata_tracker.update_trade(
                    trade_id,
                    exit_reason=exit_reason,
                    profit_pct=profit_pct,
                    actual_r=actual_r
                )
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            response = {
                'status': 'ok',
                'trade_id': trade_id,
                'profit_pct': profit_pct,
                'exit_reason': exit_reason,
                'message': 'Exit recorded'
            }
            
            self.wfile.write(json.dumps(response, indent=2).encode())
            
        except Exception as e:
            logger.error(f"Error handling exit: {e}")
            self.send_error(500, str(e))
    
    def handle_status(self, data: dict):
        """Handle trade status update."""
        try:
            trade_id = data.get('trade_id')
            status = data.get('status')
            current_profit = data.get('current_profit', 0)
            
            logger.info(f"Trade status: {trade_id} - {status} ({current_profit*100:.2f}%)")
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            response = {
                'status': 'ok',
                'trade_id': trade_id,
                'current_profit': current_profit,
                'message': 'Status updated'
            }
            
            self.wfile.write(json.dumps(response, indent=2).encode())
            
        except Exception as e:
            logger.error(f"Error handling status: {e}")
            self.send_error(500, str(e))


class WebhookServer:
    """
    Webhook Server for Trade Updates
    
    Runs an HTTP server to receive trade updates from FreqTrade.
    """
    
    def __init__(
        self,
        matrix_agent: Optional[MatrixAgent] = None,
        host: str = "0.0.0.0",
        port: int = 8080
    ):
        """
        Initialize webhook server.
        
        Args:
            matrix_agent: MatrixAgent instance
            host: Server host
            port: Server port
        """
        self.matrix_agent = matrix_agent
        self.host = host
        self.port = port
        self.server: Optional[HTTPServer] = None
        self.thread: Optional[threading.Thread] = None
        self.metadata_tracker = MetadataTracker()
        
        # Set up handler with references
        MatrixWebhookHandler.matrix_agent = matrix_agent
        MatrixWebhookHandler.metadata_tracker = self.metadata_tracker
    
    def start(self, background: bool = True):
        """
        Start webhook server.
        
        Args:
            background: Run in background thread
        """
        self.server = HTTPServer((self.host, self.port), MatrixWebhookHandler)
        
        logger.info(f"Webhook server starting on {self.host}:{self.port}")
        
        if background:
            self.thread = threading.Thread(target=self.server.serve_forever)
            self.thread.daemon = True
            self.thread.start()
        else:
            self.server.serve_forever()
    
    def stop(self):
        """Stop webhook server."""
        if self.server:
            self.server.shutdown()
            logger.info("Webhook server stopped")
    
    def get_trades(self) -> list:
        """Get all tracked trades."""
        return self.metadata_tracker.get_all_trades()
    
    def get_performance(self) -> dict:
        """Get performance summary."""
        return self.metadata_tracker.get_performance_summary()


class TradeUpdateManager:
    """
    Trade Update Manager
    
    Manages trade updates and integration with Matrix Agent.
    """
    
    def __init__(self, matrix_agent: Optional[MatrixAgent] = None):
        """
        Initialize trade update manager.
        
        Args:
            matrix_agent: MatrixAgent instance
        """
        self.matrix_agent = matrix_agent or MatrixAgent()
        self.metadata_tracker = MetadataTracker()
        self.webhook_server: Optional[WebhookServer] = None
        
    def setup_webhook(self, host: str = "0.0.0.0", port: int = 8080) -> WebhookServer:
        """
        Set up webhook server.
        
        Args:
            host: Server host
            port: Server port
            
        Returns:
            WebhookServer instance
        """
        self.webhook_server = WebhookServer(
            matrix_agent=self.matrix_agent,
            host=host,
            port=port
        )
        
        self.webhook_server.metadata_tracker = self.metadata_tracker
        
        return self.webhook_server
    
    def process_entry(
        self,
        pair: str,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        direction: str = "long",
        expected_r: float = 3.0,
        confidence: float = 0.7
    ) -> str:
        """
        Process trade entry.
        
        Args:
            pair: Trading pair
            entry_price: Entry price
            stop_loss: Stop loss price
            take_profit: Take profit price
            direction: Trade direction
            expected_r: Expected R
            confidence: Signal confidence
            
        Returns:
            Trade ID
        """
        trade_id = str(uuid.uuid4())[:8]
        
        # Create signal
        signal = TradeSignal(
            pair=pair,
            direction=TradeDirection.LONG if direction == "long" else TradeDirection.SHORT,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit_1=take_profit,
            take_profit_2=take_profit * 1.5,
            expected_r=expected_r,
            confidence=confidence,
            decision=Decision.APPROVE
        )
        
        # Track in metadata
        self.metadata_tracker.add_trade(trade_id, signal)
        
        logger.info(f"Trade entry recorded: {trade_id} - {pair} {direction} @ {entry_price}")
        
        return trade_id
    
    def process_exit(
        self,
        trade_id: str,
        exit_price: float,
        exit_reason: str,
        profit_pct: float
    ) -> Dict[str, Any]:
        """
        Process trade exit.
        
        Args:
            trade_id: Trade identifier
            exit_price: Exit price
            exit_reason: Reason for exit
            profit_pct: Profit percentage
            
        Returns:
            Exit result dictionary
        """
        # Calculate actual R (assuming 1% risk per trade)
        risk_pct = 0.01
        actual_r = profit_pct / risk_pct if risk_pct > 0 else 0
        
        # Update metadata
        metadata = self.metadata_tracker.update_trade(
            trade_id,
            exit_reason=exit_reason,
            profit_pct=profit_pct,
            actual_r=actual_r
        )
        
        # Determine execution quality
        execution_quality = self._calculate_execution_quality(
            metadata.expected_r if metadata else expected_r,
            actual_r
        )
        
        if metadata:
            self.metadata_tracker.update_trade(
                trade_id,
                execution_quality=execution_quality
            )
        
        # Log result
        logger.info(f"Trade exit: {trade_id} - {profit_pct*100:.2f}% ({exit_reason})")
        
        return {
            'trade_id': trade_id,
            'profit_pct': profit_pct,
            'actual_r': actual_r,
            'execution_quality': execution_quality,
            'exit_reason': exit_reason
        }
    
    def _calculate_execution_quality(
        self,
        expected_r: float,
        actual_r: float
    ) -> str:
        """
        Calculate execution quality rating.
        
        Args:
            expected_r: Expected R from signal
            actual_r: Actual R achieved
            
        Returns:
            Quality rating (A+, A, B, C, D)
        """
        if actual_r >= expected_r * 0.8:
            if actual_r >= 3:
                return "A+"
            else:
                return "A"
        elif actual_r >= 0:
            return "B"
        elif actual_r >= -1:
            return "C"
        else:
            return "D"
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """
        Get performance summary.
        
        Returns:
            Performance summary dictionary
        """
        return self.metadata_tracker.get_performance_summary()
    
    def get_all_trades(self) -> list:
        """Get all tracked trades."""
        return self.metadata_tracker.get_all_trades()
    
    def export_trades(self, filepath: str = "trades_export.json"):
        """
        Export trades to JSON file.
        
        Args:
            filepath: Output file path
        """
        trades = self.get_all_trades()
        
        export_data = {
            'export_date': datetime.now().isoformat(),
            'total_trades': len(trades),
            'trades': [t.to_dict() for t in trades],
            'performance': self.get_performance_summary()
        }
        
        with open(filepath, 'w') as f:
            json.dump(export_data, f, indent=2)
        
        logger.info(f"Trades exported to {filepath}")


def create_webhook_config(
    webhook_url: str = "http://localhost:8080/webhook"
) -> dict:
    """
    Create FreqTrade webhook configuration.
    
    Args:
        webhook_url: Webhook URL for Matrix Agent
        
    Returns:
        Webhook configuration dictionary
    """
    return {
        "enabled": True,
        "url": webhook_url,
        "webhookentry": {
            "value1": "{pair}",
            "value2": "{stake_amount}",
            "value3": "{current_rate}",
            "value4": "entry"
        },
        "webhookentrycancel": {
            "value1": "{pair}",
            "value2": "Entry cancelled",
            "value3": "{current_rate}",
            "value4": "entry_cancel"
        },
        "webhookentryfill": {
            "value1": "{pair}",
            "value2": "{stake_amount}",
            "value3": "{open_rate}",
            "value4": "entry_fill"
        },
        "webhookexit": {
            "value1": "{pair}",
            "value2": "{profit_amount}",
            "value3": "{profit_ratio}",
            "value4": "exit"
        },
        "webhookexitcancel": {
            "value1": "{pair}",
            "value2": "Exit cancelled",
            "value3": "{current_rate}",
            "value4": "exit_cancel"
        },
        "webhookexitfill": {
            "value1": "{pair}",
            "value2": "{profit_amount}",
            "value3": "{profit_ratio}",
            "value4": "exit_fill"
        },
        "webhookstatus": {
            "value1": "{status}",
            "value2": "{open_trades}",
            "value3": "status"
        }
    }


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)
    
    manager = TradeUpdateManager()
    
    # Set up webhook server
    server = manager.setup_webhook(host="0.0.0.0", port=8080)
    server.start(background=True)
    
    print("Webhook server running. Press Ctrl+C to stop.")
    
    try:
        while True:
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        server.stop()
