import sys
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


# Add scripts to path so we can import Sentinel
sys.path.append(str(Path(__file__).resolve().parent.parent / "scripts"))
# We also need ft_client in path for Sentinel to import it
sys.path.append(str(Path(__file__).resolve().parent.parent / "ft_client"))

from sentinel import Sentinel


class TestSentinel(unittest.TestCase):
    def setUp(self):
        self.config_content = {
            "api_server": {
                "enabled": True,
                "listen_ip_address": "127.0.0.1",
                "listen_port": 8080,
                "username": "user",
                "password": "pass",
            }
        }

    @patch("sentinel.Sentinel._load_config")
    @patch("sentinel.Sentinel._init_client")
    @patch("sentinel.Sentinel._load_history")
    def test_drawdown_check(self, mock_load_history, mock_init_client, mock_load_config):
        mock_load_config.return_value = self.config_content
        mock_client = MagicMock()
        mock_init_client.return_value = mock_client
        mock_load_history.return_value = []  # Start empty

        # Instantiate
        sentinel = Sentinel("config.json", 300, True, "BTC/USDT")

        # Mock history with a drop
        # Max balance 1000, current 940 (6% drop)
        now = time.time()
        sentinel.balance_history = [
            {"ts": now - 1800, "balance": 1000.0},
            {"ts": now, "balance": 940.0},
        ]

        self.assertTrue(sentinel.check_drawdown())

        # Test no drop
        sentinel.balance_history = [
            {"ts": now - 1800, "balance": 1000.0},
            {"ts": now, "balance": 990.0},
        ]
        self.assertFalse(sentinel.check_drawdown())

    @patch("sentinel.Sentinel._load_config")
    @patch("sentinel.Sentinel._init_client")
    @patch("sentinel.Sentinel._load_history")
    def test_btc_crash_check(self, mock_load_history, mock_init_client, mock_load_config):
        mock_load_config.return_value = self.config_content
        mock_client = MagicMock()
        mock_init_client.return_value = mock_client
        sentinel = Sentinel("config.json", 300, True, "BTC/USDT")

        # Mock pair_candles
        # [timestamp, open, high, low, close, volume]
        now_ms = int(time.time() * 1000)

        # High was 50000, now 44000 (12% drop)
        # Using 1h candles, so 3600*1000 ms per candle
        candles = [
            [now_ms - 3600000, 50000, 50000, 49000, 49500, 100],  # 1h ago
            [now_ms, 49500, 49600, 44000, 44000, 100],  # Current
        ]
        mock_client.pair_candles.return_value = candles

        self.assertTrue(sentinel.check_btc_crash())

        # No crash
        candles_ok = [
            [now_ms - 3600000, 50000, 50000, 49000, 49500, 100],
            [now_ms, 49500, 49600, 49000, 49000, 100],
        ]
        mock_client.pair_candles.return_value = candles_ok
        self.assertFalse(sentinel.check_btc_crash())

    @patch("sentinel.Sentinel._load_config")
    @patch("sentinel.Sentinel._init_client")
    @patch("sentinel.Sentinel._load_history")
    def test_trigger_emergency(
        self, mock_load_history, mock_init_client, mock_load_config
    ):
        mock_load_config.return_value = self.config_content
        mock_client = MagicMock()
        mock_init_client.return_value = mock_client

        # Test Dry Run
        sentinel_dry = Sentinel("config.json", 300, True, "BTC/USDT")
        sentinel_dry.trigger_emergency("Test")
        mock_client.stop.assert_not_called()

        # Test Live
        sentinel_live = Sentinel("config.json", 300, False, "BTC/USDT")
        # Mock status for panic sell
        mock_client.status.return_value = [
            {"trade_id": 1, "pair": "ETH/USDT"},
            {"trade_id": 2, "pair": "SOL/USDT"},
        ]

        sentinel_live.trigger_emergency("Test")
        mock_client.stop.assert_called_once()

        # Verify forceexit called for each trade
        self.assertEqual(mock_client.forceexit.call_count, 2)
        mock_client.forceexit.assert_any_call(1, ordertype="market")
        mock_client.forceexit.assert_any_call(2, ordertype="market")


if __name__ == "__main__":
    unittest.main()
