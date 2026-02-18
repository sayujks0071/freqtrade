import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


# Add scripts directory to path
sys.path.append(str(Path(__file__).parent.parent / "scripts"))

from sentinel import Sentinel  # noqa: E402, RUF100


class TestSentinel(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for each test
        self.test_dir = tempfile.TemporaryDirectory()
        self.test_dir_path = Path(self.test_dir.name)

        self.config = {
            "api_server": {
                "listen_ip_address": "127.0.0.1",
                "listen_port": 8080,
                "username": "user",
                "password": "password",
            }
        }
        self.config_path = self.test_dir_path / "test_config.json"
        with self.config_path.open("w") as f:
            json.dump(self.config, f)

        self.sentinel = Sentinel(self.config_path, "http://openclaw", True, False)
        # Point state file to the temporary directory
        self.sentinel.state_file = self.test_dir_path / "test_sentinel_state.json"

    def tearDown(self):
        # Cleanup the temporary directory
        self.test_dir.cleanup()

    @patch("sentinel.requests.post")
    def test_get_token(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"access_token": "token123"}
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        self.sentinel.get_token()
        self.assertEqual(self.sentinel.access_token, "token123")

    @patch("sentinel.ccxt.binance")
    def test_check_btc_crash_true(self, mock_ccxt):
        # Mock exchange
        mock_exchange = MagicMock()
        mock_ccxt.return_value = mock_exchange

        # [timestamp, open, high, low, close, volume]
        # High was 100, current close is 89 (11% drop)
        mock_exchange.fetch_ohlcv.return_value = [
            [1000, 100, 100, 90, 95, 10],  # -4
            [1001, 95, 96, 94, 95, 10],  # -3
            [1002, 95, 95, 90, 90, 10],  # -2
            [1003, 90, 90, 80, 85, 10],  # -1
            [1004, 85, 89, 88, 89, 10],  # Current
        ]

        result = self.sentinel.check_btc_crash()
        self.assertTrue(result)

    @patch("sentinel.ccxt.binance")
    def test_check_btc_crash_false(self, mock_ccxt):
        # Mock exchange
        mock_exchange = MagicMock()
        mock_ccxt.return_value = mock_exchange

        # High was 100, current close is 95 (5% drop)
        mock_exchange.fetch_ohlcv.return_value = [
            [1000, 100, 100, 90, 95, 10],
            [1004, 95, 96, 94, 95, 10],
        ]

        result = self.sentinel.check_btc_crash()
        self.assertFalse(result)

    @patch("sentinel.requests.get")
    def test_check_drawdown_true(self, mock_get):
        self.sentinel.access_token = "token"

        # Setup history: Max was 1000
        now = time.time()
        self.sentinel.state["balance_history"] = [[now - 100, 1000.0]]

        # Current is 900 (10% drop)
        mock_response = MagicMock()
        mock_response.json.return_value = {"total": 900.0}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        result = self.sentinel.check_drawdown()
        self.assertTrue(result)

    @patch("sentinel.requests.get")
    def test_check_drawdown_false(self, mock_get):
        self.sentinel.access_token = "token"

        now = time.time()
        self.sentinel.state["balance_history"] = [[now - 100, 1000.0]]

        # Current is 960 (4% drop)
        mock_response = MagicMock()
        mock_response.json.return_value = {"total": 960.0}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        result = self.sentinel.check_drawdown()
        self.assertFalse(result)

    @patch("sentinel.requests.post")
    @patch("sentinel.requests.get")
    def test_trigger_emergency(self, mock_get, mock_post):
        self.sentinel.access_token = "token"
        self.sentinel.panic_sell = True

        # Mock open trades response
        mock_get_resp = MagicMock()
        mock_get_resp.json.return_value = [{"trade_id": 1}, {"trade_id": 2}]
        mock_get_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_get_resp

        mock_post_resp = MagicMock()
        mock_post_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_post_resp

        self.sentinel.trigger_emergency("Test Reason")

        # Check Alert
        mock_post.assert_any_call(
            "http://openclaw",
            json={"message": "CRITICAL ALERT: Test Reason"},
            timeout=10,
        )

        # Check Stop
        mock_post.assert_any_call(
            f"{self.sentinel.api_url}/stop",
            headers=self.sentinel.get_headers(),
            timeout=10,
        )

        self.assertTrue(self.sentinel.state["triggered"])


if __name__ == "__main__":
    unittest.main()
