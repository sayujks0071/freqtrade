import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


# Add scripts directory to path to allow importing sentinel
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.append(str(SCRIPTS_DIR))

# Ensure sentinel is importable even if dependencies are missing in test env (fallback)
try:
    import sentinel
except ImportError:
    sys.modules["ccxt"] = MagicMock()
    sys.modules["freqtrade_client"] = MagicMock()
    sys.modules["freqtrade_client.ft_client"] = MagicMock()
    import sentinel


class TestSentinel(unittest.TestCase):
    def setUp(self):
        # Patch load_config
        self.config_patcher = patch("sentinel.load_config")
        self.mock_load_config = self.config_patcher.start()
        self.mock_load_config.return_value = {
            "api_server": {
                "listen_ip_address": "127.0.0.1",
                "listen_port": "8080",
                "username": "user",
                "password": "pass",
            }
        }

        # Patch FtRestClient
        self.client_patcher = patch("sentinel.FtRestClient")
        self.mock_client_cls = self.client_patcher.start()
        self.mock_client = self.mock_client_cls.return_value

        # Patch ccxt.gateio
        self.ccxt_patcher = patch("sentinel.ccxt.gateio")
        self.mock_gateio = self.ccxt_patcher.start()
        self.mock_exchange = self.mock_gateio.return_value

    def tearDown(self):
        self.config_patcher.stop()
        self.client_patcher.stop()
        self.ccxt_patcher.stop()

    def test_check_btc_crash_no_data(self):
        s = sentinel.Sentinel("config.json")
        self.mock_exchange.fetch_ohlcv.return_value = []
        self.assertFalse(s.check_btc_crash())

    def test_check_btc_crash_no_crash(self):
        s = sentinel.Sentinel("config.json")
        # [timestamp, open, high, low, close, volume]
        # Highs: 100, 100, 100, 100, 100
        # Current: 95 (5% drop)
        self.mock_exchange.fetch_ohlcv.return_value = [
            [0, 100, 100, 90, 95, 1000] for _ in range(5)
        ]
        self.assertFalse(s.check_btc_crash())

    def test_check_btc_crash_crash(self):
        s = sentinel.Sentinel("config.json")
        # Highs: 100
        # Current: 89 (11% drop)
        # We need fetch_ohlcv to return data where max(high) is 100 and last close is 89.
        ohlcv = [[0, 100, 100, 90, 100, 1000] for _ in range(4)]
        ohlcv.append([0, 100, 100, 80, 89, 1000])
        self.mock_exchange.fetch_ohlcv.return_value = ohlcv
        self.assertTrue(s.check_btc_crash())

    def test_check_drawdown_no_history(self):
        s = sentinel.Sentinel("config.json")
        self.mock_client.balance.return_value = {"total": 100}
        # First run, history is just current
        self.assertFalse(s.check_drawdown())
        self.assertEqual(len(s.balance_history), 1)

    def test_check_drawdown_accumulate(self):
        s = sentinel.Sentinel("config.json")
        # Step 1: 100
        self.mock_client.balance.return_value = {"total": 100}
        s.check_drawdown()

        # Step 2: 98 (2% drop)
        self.mock_client.balance.return_value = {"total": 98}
        self.assertFalse(s.check_drawdown())
        self.assertEqual(len(s.balance_history), 2)

    def test_check_drawdown_trigger(self):
        s = sentinel.Sentinel("config.json")
        # Inject history
        from datetime import datetime

        now = datetime.now()
        s.balance_history = [(now, 100)]

        # Step 2: 94 (6% drop)
        self.mock_client.balance.return_value = {"total": 94}
        self.assertTrue(s.check_drawdown())

    @patch("sentinel.sys.exit")
    def test_emergency_action(self, mock_exit):
        s = sentinel.Sentinel("config.json", liquidate=True)
        # Mock status for liquidate
        self.mock_client.status.return_value = [{"trade_id": 1}]

        s.emergency_action("TEST")

        self.mock_client.forceexit.assert_called_with(1)
        self.mock_client.stop.assert_called_once()
        mock_exit.assert_called_with(0)

    @patch("sentinel.sys.exit")
    def test_emergency_action_dry_run(self, mock_exit):
        s = sentinel.Sentinel("config.json", liquidate=True, dry_run=True)
        s.emergency_action("TEST")

        self.mock_client.forceexit.assert_not_called()
        self.mock_client.stop.assert_not_called()
        mock_exit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
