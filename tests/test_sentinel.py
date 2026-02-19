import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


# Add scripts directory to path to import sentinel
sys.path.append(str(Path(__file__).parent.parent / "scripts"))

from sentinel import Sentinel  # isort:skip


class TestSentinel(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.config_path = Path(self.test_dir.name) / "config.json"
        self.state_path = Path(self.test_dir.name) / "sentinel_state.json"

        # Create dummy config
        config = {
            "api_server": {
                "enabled": True,
                "listen_ip_address": "127.0.0.1",
                "listen_port": 8080,
                "username": "user",
                "password": "password",
            },
            "exchange": {"name": "binance"},
        }
        with self.config_path.open("w") as f:
            json.dump(config, f)

        self.sentinel = Sentinel(str(self.config_path), str(self.state_path))
        # Mock API calls and exchange
        self.sentinel.exchange = MagicMock()
        self.sentinel.exchange.fetch_ohlcv = MagicMock()
        # Mock authentication token
        self.sentinel.jwt_token = "mock_token"

    def tearDown(self):
        self.test_dir.cleanup()

    @patch("requests.post")
    def test_alert(self, mock_post):
        # Mock successful response
        mock_post.return_value.status_code = 200
        self.sentinel._send_alert("Test Alert")
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        self.assertIn("Test Alert", kwargs["json"]["message"])

    @patch("requests.post")
    def test_stop_bot(self, mock_post):
        mock_post.return_value.status_code = 200
        # _stop_bot calls sys.exit(0), catch it
        with self.assertRaises(SystemExit):
            self.sentinel._stop_bot()

        # Check call arguments
        expected_url = "http://127.0.0.1:8080/api/v1/stop"
        mock_post.assert_called_with(
            expected_url, headers={"Authorization": "Bearer mock_token"}, timeout=10
        )

    def test_drawdown_calculation(self):
        # Mock balance history: started at 100
        now = time.time()
        self.sentinel.balance_history = [(now - 100, 100.0), (now - 50, 100.0)]
        # Current balance 90 (10% drop)
        drawdown = self.sentinel.check_drawdown(90.0)
        self.assertAlmostEqual(drawdown, 0.10)

        # Test 5% trigger threshold logic (not the trigger call itself, just the value)
        self.assertTrue(drawdown > 0.05)

    def test_btc_crash_detection(self):
        # Mock OHLCV: Highs were [100, 100, 100, 100], current close 80 (20% drop)
        # ohlcv format: [timestamp, open, high, low, close, volume]
        self.sentinel.exchange.fetch_ohlcv.return_value = [
            [1000, 90, 100, 80, 95, 10],
            [1001, 95, 100, 85, 95, 10],
            [1002, 95, 100, 85, 95, 10],
            [1003, 95, 100, 85, 95, 10],
            [1004, 95, 95, 80, 80, 10],  # Current candle, close=80, high=95
        ]

        # Max high in last 5 candles is 100. Current close is 80.
        # Drop = (100 - 80) / 100 = 0.20
        drop = self.sentinel._get_btc_price_drop()
        self.assertAlmostEqual(drop, 0.20)
        self.assertTrue(drop > 0.10)

    @patch("sentinel.Sentinel.trigger_emergency")
    @patch("requests.get")
    def test_monitoring_loop_logic(self, mock_get, mock_trigger):
        # Mock balance response
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"total": 90.0}  # Current balance

        # Mock BTC crash condition
        self.sentinel.exchange.fetch_ohlcv.return_value = [
            [1000, 100, 100, 100, 100, 10],
            [1001, 100, 100, 100, 100, 10],
            [1002, 100, 100, 100, 100, 10],
            [1003, 100, 100, 100, 100, 10],
            [1004, 90, 90, 80, 80, 10],  # Drop to 80
        ]

        # Run one iteration of logic manually
        btc_drop = self.sentinel._get_btc_price_drop()
        if btc_drop > 0.10:
            self.sentinel.trigger_emergency(f"Bitcoin dropped {btc_drop * 100:.2f}%")

        mock_trigger.assert_called_once()
        args, _ = mock_trigger.call_args
        self.assertIn("Bitcoin dropped 20.00%", args[0])


if __name__ == "__main__":
    unittest.main()
