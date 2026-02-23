import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch


# Add scripts to path to import sentinel as a module
SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import sentinel  # noqa: E402


class TestSentinel(unittest.TestCase):
    def setUp(self):
        # Setup common mocks
        self.mock_client = MagicMock()
        # Default balance
        self.mock_client.balance.return_value = {"total": 1000.0}
        # Default trades
        self.mock_client.status.return_value = []

        # Reset state file path to a test file
        self.test_dir = tempfile.TemporaryDirectory()
        self.original_state_file = sentinel.STATE_FILE
        sentinel.STATE_FILE = Path(self.test_dir.name) / "test_sentinel_state.json"

        # Redirect logging to avoid clutter
        self.original_logger = sentinel.logger
        sentinel.logger = MagicMock()

    def tearDown(self):
        sentinel.STATE_FILE = self.original_state_file
        self.test_dir.cleanup()
        sentinel.logger = self.original_logger

    def test_load_state_empty(self):
        state = sentinel.load_state()
        self.assertEqual(state, {"history": []})

    def test_save_and_load_state(self):
        state = {"history": [{"timestamp": 123, "balance": 100.0}]}
        sentinel.save_state(state)
        loaded = sentinel.load_state()
        self.assertEqual(loaded, state)

    def test_check_drawdown_no_history(self):
        state = {"history": []}
        triggered = sentinel.check_drawdown(self.mock_client, state)
        self.assertFalse(triggered)
        # Should have added current balance
        self.assertEqual(len(state["history"]), 1)
        self.assertEqual(state["history"][0]["balance"], 1000.0)

    def test_check_drawdown_accumulates_history(self):
        state = {
            "history": [
                {
                    "timestamp": datetime.now(timezone.utc).timestamp() - 100,  # noqa: UP017
                    "balance": 1000.0,
                }
            ]
        }
        self.mock_client.balance.return_value = {"total": 1010.0}

        triggered = sentinel.check_drawdown(self.mock_client, state)
        self.assertFalse(triggered)
        self.assertEqual(len(state["history"]), 2)
        self.assertEqual(state["history"][-1]["balance"], 1010.0)

    def test_check_drawdown_prunes_old_history(self):
        old_ts = datetime.now(timezone.utc).timestamp() - 4000  # noqa: UP017 # > 1 hour ago
        state = {"history": [{"timestamp": old_ts, "balance": 2000.0}]}  # Old high balance

        triggered = sentinel.check_drawdown(self.mock_client, state)
        # Old entry should be removed, so max balance is current (1000). No drawdown.
        self.assertFalse(triggered)
        self.assertEqual(len(state["history"]), 1)
        self.assertEqual(state["history"][0]["balance"], 1000.0)

    def test_check_drawdown_trigger(self):
        # High balance 1 hour ago
        recent_ts = datetime.now(timezone.utc).timestamp() - 100  # noqa: UP017
        state = {"history": [{"timestamp": recent_ts, "balance": 1000.0}]}

        # Current balance 940 (6% drop)
        self.mock_client.balance.return_value = {"total": 940.0}

        triggered = sentinel.check_drawdown(self.mock_client, state)
        self.assertTrue(triggered)

    def test_check_drawdown_no_trigger_small_drop(self):
        # High balance 1 hour ago
        recent_ts = datetime.now(timezone.utc).timestamp() - 100  # noqa: UP017
        state = {"history": [{"timestamp": recent_ts, "balance": 1000.0}]}

        # Current balance 960 (4% drop)
        self.mock_client.balance.return_value = {"total": 960.0}

        triggered = sentinel.check_drawdown(self.mock_client, state)
        self.assertFalse(triggered)

    def test_check_btc_drop_no_data(self):
        mock_exchange = MagicMock()
        mock_exchange.fetch_ohlcv.return_value = []
        with patch("sentinel.ccxt.binance", return_value=mock_exchange):
            triggered = sentinel.check_btc_drop()
            self.assertFalse(triggered)

    def test_check_btc_drop_no_trigger(self):
        mock_exchange = MagicMock()
        # OHLCV: [time, open, high, low, close, volume]
        # Max high 100, current 95
        mock_exchange.fetch_ohlcv.return_value = [
            [0, 100, 100, 90, 95, 100],
            [1, 95, 98, 92, 95, 100],
        ]
        with patch("sentinel.ccxt.binance", return_value=mock_exchange):
            triggered = sentinel.check_btc_drop()
            self.assertFalse(triggered)

    def test_check_btc_drop_trigger(self):
        mock_exchange = MagicMock()
        # Max high 100, current 85 (15% drop)
        mock_exchange.fetch_ohlcv.return_value = [
            [0, 100, 100, 90, 95, 100],  # High 100
            [1, 95, 85, 80, 85, 100],  # Current 85
        ]
        with patch("sentinel.ccxt.binance", return_value=mock_exchange):
            triggered = sentinel.check_btc_drop()
            self.assertTrue(triggered)

    @patch("sentinel.sys.exit")
    def test_trigger_emergency(self, mock_exit):
        self.mock_client.status.return_value = [{"trade_id": 1}, {"trade_id": 2}]

        # Mock send_alert to avoid actual request/file write
        with patch("sentinel.send_alert") as mock_send_alert:
            sentinel.trigger_emergency(self.mock_client, "TEST REASON")

            mock_send_alert.assert_called_with("EMERGENCY TRIGGERED: TEST REASON")

            # Check order: forceexit (liquidation) must be called BEFORE stop
            forceexit_indices = [
                i for i, call in enumerate(self.mock_client.mock_calls) if call[0] == "forceexit"
            ]
            stop_indices = [
                i for i, call in enumerate(self.mock_client.mock_calls) if call[0] == "stop"
            ]

            self.assertTrue(forceexit_indices, "Forceexit should have been called")
            self.assertTrue(stop_indices, "Stop should have been called")

            # Ensure all forceexit calls happen before any stop call
            self.assertLess(
                max(forceexit_indices),
                min(stop_indices),
                "Liquidation must happen before stopping bot"
            )

            mock_exit.assert_called_with(0)

    @patch("sentinel.requests.post")
    def test_send_alert(self, mock_post):
        mock_post.return_value.status_code = 200
        # Patch open to avoid writing log
        with patch("builtins.open", mock_open()):
            sentinel.send_alert("Test message")
            mock_post.assert_called_once()
            _args, kwargs = mock_post.call_args
            self.assertIn("message", kwargs["json"])
            self.assertEqual(kwargs["json"]["message"], "Test message")


if __name__ == "__main__":
    unittest.main()
