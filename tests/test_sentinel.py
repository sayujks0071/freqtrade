import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


# Load the sentinel module dynamically
spec = importlib.util.spec_from_file_location("sentinel", "scripts/sentinel.py")
sentinel_module = importlib.util.module_from_spec(spec)
sys.modules["sentinel"] = sentinel_module
spec.loader.exec_module(sentinel_module)


class TestSentinel(unittest.TestCase):
    def setUp(self):
        # Create temporary directory for config and state
        self.test_dir = tempfile.mkdtemp()
        self.config_path = Path(self.test_dir) / "config.json"
        self.state_path = Path(self.test_dir) / "sentinel_state.json"

        # Create a dummy config
        self.config_data = {
            "api_server": {
                "enabled": True,
                "listen_ip_address": "127.0.0.1",
                "listen_port": 8080,
                "username": "testuser",
                "password": "testpassword",
            },
            "exchange": {"name": "binance"},
        }
        with self.config_path.open("w") as f:
            json.dump(self.config_data, f)

        # Initialize Sentinel with mocked calls where necessary
        # We patch requests globally or use context managers in tests
        self.sentinel = sentinel_module.Sentinel(str(self.config_path), str(self.state_path))
        self.sentinel.exchange = MagicMock()  # Mock the exchange object
        self.sentinel.exchange.fetch_ticker.return_value = {"last": 50000.0}

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    @patch("requests.post")
    def test_login_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"access_token": "fake_token"}
        mock_post.return_value = mock_response

        self.sentinel.login()

        self.assertEqual(self.sentinel.auth_token, "fake_token")
        mock_post.assert_called_with(
            "http://127.0.0.1:8080/api/v1/token/login",
            data={"username": "testuser", "password": "testpassword"},
            timeout=10,
        )

    @patch("requests.get")
    def test_fetch_balance_success(self, mock_get):
        self.sentinel.auth_token = "fake_token"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"total": 1000.0}
        mock_get.return_value = mock_response

        balance = self.sentinel.fetch_balance()
        self.assertEqual(balance, 1000.0)
        mock_get.assert_called_with(
            "http://127.0.0.1:8080/api/v1/balance",
            headers={"Authorization": "Bearer fake_token"},
            timeout=10,
        )

    def test_check_drawdown_no_trigger(self):
        # Scenario: Balance is stable or increasing
        self.assertFalse(self.sentinel.check_drawdown(1000.0))
        self.assertFalse(self.sentinel.check_drawdown(1050.0))
        self.assertFalse(self.sentinel.check_drawdown(1020.0))  # Small drop, < 5%

    def test_check_drawdown_trigger(self):
        # Scenario: Balance drops > 5% from max in last hour
        self.sentinel.check_drawdown(1000.0)  # Set max

        # Drop to 940 (6% drop)
        is_triggered = self.sentinel.check_drawdown(940.0)
        self.assertTrue(is_triggered)

    def test_check_btc_drop_no_trigger(self):
        self.assertFalse(self.sentinel.check_btc_drop(50000.0))
        self.assertFalse(self.sentinel.check_btc_drop(51000.0))
        self.assertFalse(self.sentinel.check_btc_drop(49000.0))  # Small drop

    def test_check_btc_drop_trigger(self):
        self.sentinel.check_btc_drop(50000.0)  # Set max

        # Drop to 44000 (12% drop)
        is_triggered = self.sentinel.check_btc_drop(44000.0)
        self.assertTrue(is_triggered)

    @patch("requests.post")
    @patch("requests.get")
    def test_trigger_emergency(self, mock_get, mock_post):
        self.sentinel.auth_token = "fake_token"

        # Mock fetch trades for liquidation
        mock_get_response = MagicMock()
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = [{"trade_id": 1, "pair": "BTC/USDT"}]
        mock_get.return_value = mock_get_response

        # Mock post responses (alert, forceexit, stop)
        mock_post_response = MagicMock()
        mock_post_response.status_code = 200
        mock_post.return_value = mock_post_response

        # We expect sys.exit(0) at the end, so we catch it
        with self.assertRaises(SystemExit):
            self.sentinel.trigger_emergency("Test Trigger")

        # Verify Alert sent
        mock_post.assert_any_call(
            "http://localhost:5000/send",
            json={"message": "CRITICAL ALERT: Sentinel Triggered! Reason: Test Trigger"},
            timeout=5,
        )

        # Verify Liquidation (forceexit) called
        mock_post.assert_any_call(
            "http://127.0.0.1:8080/api/v1/forceexit",
            headers={"Authorization": "Bearer fake_token"},
            json={"tradeid": 1},
            timeout=5,
        )

        # Verify Stop called
        mock_post.assert_any_call(
            "http://127.0.0.1:8080/api/v1/stop",
            headers={"Authorization": "Bearer fake_token"},
            timeout=5,
        )


if __name__ == "__main__":
    unittest.main()
