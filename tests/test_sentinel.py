import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch


# --- Setup mocks BEFORE importing sentinel ---
# We need to mock 'ccxt', 'requests', 'freqtrade_client' and its submodules
# to avoid import errors in the test environment if they are missing.

mock_ccxt = MagicMock()
sys.modules["ccxt"] = mock_ccxt

mock_requests = MagicMock()
sys.modules["requests"] = mock_requests

mock_freqtrade_client = MagicMock()
sys.modules["freqtrade_client"] = mock_freqtrade_client

mock_ft_rest_client_module = MagicMock()
sys.modules["freqtrade_client.ft_rest_client"] = mock_ft_rest_client_module

# Now we can import sentinel
# Add scripts to path to import sentinel as a module
sys.path.append(str(Path(__file__).parent.parent / "scripts"))
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
        sentinel.STATE_FILE = Path("test_sentinel_state.json")
        if sentinel.STATE_FILE.exists():
            sentinel.STATE_FILE.unlink()

        # Redirect logging to avoid clutter
        sentinel.logger = MagicMock()

    def tearDown(self):
        if sentinel.STATE_FILE.exists():
            sentinel.STATE_FILE.unlink()

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
                    "balance": 1000.0
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
            [1, 95, 85, 80, 85, 100],    # Current 85
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
            self.mock_client.stop.assert_called_once()
            self.assertEqual(self.mock_client.forceexit.call_count, 2)
            self.mock_client.forceexit.assert_any_call(1)
            self.mock_client.forceexit.assert_any_call(2)
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
