import sys
import unittest
from pathlib import Path
from unittest.mock import patch


# Add scripts to path to import sentinel
scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
sys.path.append(str(scripts_dir))

# Mock rapidjson before importing sentinel to avoid issues with C-extension vs mock_open
# We can't easily mock C-extension modules at sys.modules level if they are already loaded
# But patch works fine.

import sentinel


class TestSentinel(unittest.TestCase):
    def setUp(self):
        self.config_path = Path("user_data/configs/config.delta.live.json")

        # Mock pathlib.Path.exists
        self.patcher_exists = patch("pathlib.Path.exists", return_value=True)
        self.mock_exists = self.patcher_exists.start()

        # Mock open
        self.patcher_open = patch(
            "builtins.open", unittest.mock.mock_open(read_data='{"api_server": {}}')
        )
        self.mock_open = self.patcher_open.start()

        # Mock FtRestClient
        self.patcher_client = patch("sentinel.FtRestClient")
        self.mock_client_cls = self.patcher_client.start()
        self.mock_client = self.mock_client_cls.return_value

        # Patch rapidjson.load
        self.patcher_rapidjson = patch("rapidjson.load", return_value={"api_server": {}})
        self.mock_rapidjson = self.patcher_rapidjson.start()

        self.sentinel = sentinel.Sentinel(str(self.config_path))

    def tearDown(self):
        self.patcher_exists.stop()
        self.patcher_open.stop()
        self.patcher_client.stop()
        self.patcher_rapidjson.stop()

    def test_check_drawdown(self):
        # Initial balance 100
        self.sentinel.update_balance_history(100)
        self.assertFalse(self.sentinel.check_drawdown(100))

        # Balance 98 (2% drop)
        self.sentinel.update_balance_history(98)
        self.assertFalse(self.sentinel.check_drawdown(98))

        # Balance 94 (6% drop from max 100)
        self.assertTrue(self.sentinel.check_drawdown(94))

    def test_check_btc_crash(self):
        # Mock candles: [time, open, high, low, close, vol]
        # Current price (last) = 90. 4h ago (first) = 100.
        # Drop = (100 - 90) / 100 = 0.10. Not > 0.10.
        self.mock_client.pair_candles.return_value = [
            [0, 100, 100, 100, 100, 100],
            [0, 100, 100, 100, 100, 100],
            [0, 100, 100, 100, 100, 100],
            [0, 100, 100, 100, 100, 100],
            [0, 90, 90, 90, 90, 90],
        ]
        self.assertFalse(self.sentinel.check_btc_crash())

        # Current price 89. Drop = 11%.
        self.mock_client.pair_candles.return_value = [
            [0, 100, 100, 100, 100, 100],
            [0, 100, 100, 100, 100, 100],
            [0, 100, 100, 100, 100, 100],
            [0, 100, 100, 100, 100, 100],
            [0, 89, 89, 89, 89, 89],
        ]
        self.assertTrue(self.sentinel.check_btc_crash())

    @patch("requests.post")
    @patch("sentinel.sys.exit")
    def test_emergency_shutdown(self, mock_exit, mock_post):
        # Mock open trades
        self.mock_client.status.return_value = [{"trade_id": 1}, {"trade_id": 2}]

        self.sentinel.emergency_shutdown("Test Reason")

        # Verify alert sent
        mock_post.assert_called_with(
            "http://localhost:5000/send",
            json={"message": "CRITICAL ALERT: Test Reason. Initiating Kill Switch."},
            timeout=5,
        )

        # Verify stopbuy
        self.mock_client.stopbuy.assert_called_once()

        # Verify forceexit for each trade
        self.assertEqual(self.mock_client.forceexit.call_count, 2)
        self.mock_client.forceexit.assert_any_call(1)
        self.mock_client.forceexit.assert_any_call(2)

        # Verify stop
        self.mock_client.stop.assert_called_once()

        # Verify exit
        mock_exit.assert_called_with(0)


if __name__ == "__main__":
    unittest.main()
