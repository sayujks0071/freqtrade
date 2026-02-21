import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


# Manipulate sys.path to import scripts.sentinel
sys.path.append(str(Path(__file__).parent.parent / "scripts"))

# Import Sentinel class
try:
    from sentinel import Sentinel
except ImportError:
    sys.path.append("scripts")
    from sentinel import Sentinel


class TestSentinel(unittest.TestCase):
    def setUp(self):
        self.config_path = Path("tests/test_config.json")
        self.state_path = Path("tests/test_state.json")

        # Create dummy config
        with self.config_path.open("w") as f:
            json.dump(
                {
                    "api_server": {
                        "enabled": True,
                        "listen_ip_address": "127.0.0.1",
                        "listen_port": 8080,
                        "username": "user",
                        "password": "pass",
                    }
                },
                f,
            )

        # Create dummy state
        with self.state_path.open("w") as f:
            json.dump({"balance_history": []}, f)

        self.sentinel = Sentinel(self.config_path, self.state_path)
        # Mock logger to suppress output during tests
        self.sentinel.logger = MagicMock()

    def tearDown(self):
        if self.config_path.exists():
            self.config_path.unlink()
        if self.state_path.exists():
            self.state_path.unlink()

    @patch("requests.post")
    def test_get_api_token_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"access_token": "test_token"}
        mock_post.return_value = mock_response

        token = self.sentinel.get_api_token()
        self.assertEqual(token, "test_token")
        self.assertEqual(self.sentinel.access_token, "test_token")

    @patch("requests.post")
    def test_get_api_token_failure(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_post.return_value = mock_response

        token = self.sentinel.get_api_token()
        self.assertIsNone(token)

    @patch("sentinel.Sentinel.get_api_token")
    @patch("requests.get")
    def test_get_current_balance(self, mock_get, mock_token):
        mock_token.return_value = "token"
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"total": 1000.0}
        mock_get.return_value = mock_response

        balance = self.sentinel.get_current_balance()
        self.assertEqual(balance, 1000.0)

    @patch("sentinel.Sentinel.get_current_balance")
    def test_check_drawdown_no_history(self, mock_balance):
        mock_balance.return_value = 1000.0
        # Should start with empty history
        self.sentinel.state["balance_history"] = []

        triggered = self.sentinel.check_drawdown()
        self.assertFalse(triggered)
        # History should have 1 entry
        self.assertEqual(len(self.sentinel.state["balance_history"]), 1)

    @patch("sentinel.Sentinel.get_current_balance")
    def test_check_drawdown_safe(self, mock_balance):
        # Max balance 1000, current 960 (4% drop)
        import time

        now = time.time()
        self.sentinel.state["balance_history"] = [(now - 1800, 1000.0)]
        mock_balance.return_value = 960.0

        triggered = self.sentinel.check_drawdown()
        self.assertFalse(triggered)

    @patch("sentinel.Sentinel.get_current_balance")
    def test_check_drawdown_trigger(self, mock_balance):
        # Max balance 1000, current 940 (6% drop)
        import time

        now = time.time()
        self.sentinel.state["balance_history"] = [(now - 1800, 1000.0)]
        mock_balance.return_value = 940.0

        triggered = self.sentinel.check_drawdown()
        self.assertTrue(triggered)

    @patch("ccxt.binance")
    def test_check_btc_crash_safe(self, mock_ccxt):
        mock_exchange = MagicMock()
        # [time, open, high, low, close, volume]
        # Highs: 50000, 50000, 50000, 50000, 50000
        # Current: 48000 (4% drop)
        mock_exchange.fetch_ohlcv.return_value = [
            [0, 50000, 50000, 49000, 49500, 100],
            [0, 50000, 50000, 49000, 49500, 100],
            [0, 50000, 50000, 49000, 49500, 100],
            [0, 50000, 50000, 49000, 49500, 100],
            [0, 49500, 49500, 48000, 48000, 100],
        ]
        mock_ccxt.return_value = mock_exchange

        triggered = self.sentinel.check_btc_crash()
        self.assertFalse(triggered)

    @patch("ccxt.binance")
    def test_check_btc_crash_trigger(self, mock_ccxt):
        mock_exchange = MagicMock()
        # Highs: 50000
        # Current: 44000 (12% drop)
        mock_exchange.fetch_ohlcv.return_value = [
            [0, 50000, 50000, 49000, 49500, 100],
            [0, 50000, 50000, 49000, 49500, 100],
            [0, 50000, 50000, 49000, 49500, 100],
            [0, 50000, 50000, 49000, 49500, 100],
            [0, 45000, 45000, 44000, 44000, 100],
        ]
        mock_ccxt.return_value = mock_exchange

        triggered = self.sentinel.check_btc_crash()
        self.assertTrue(triggered)

    @patch("sentinel.Sentinel.get_api_token")
    @patch("requests.post")
    def test_trigger_emergency(self, mock_post, mock_token):
        mock_token.return_value = "token"
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        # Mock journal path to avoid writing to real .jules
        with patch("pathlib.Path.open", unittest.mock.mock_open()) as mock_file:
            self.sentinel.trigger_emergency("Test Reason")

            # Check API calls
            # 1. Force Exit
            # 2. Stop
            self.assertEqual(mock_post.call_count, 2)
            # Verify calls
            calls = mock_post.call_args_list
            self.assertIn("/api/v1/forceexit", calls[0][0][0])
            self.assertIn("/api/v1/stop", calls[1][0][0])

            # Check Journal write
            mock_file.assert_called()


if __name__ == "__main__":
    unittest.main()
