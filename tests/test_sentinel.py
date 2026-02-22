import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add scripts directory to sys.path to allow importing sentinel
scripts_path = Path(__file__).parents[1] / "scripts"
if str(scripts_path) not in sys.path:
    sys.path.append(str(scripts_path))

# Import sentinel module
# Note: This requires freqtrade_client to be importable or mocked if dependencies are missing.
# In the CI environment, dependencies are installed.
try:
    import sentinel  # noqa: E402
except ImportError:
    # Fallback for environments where dependencies might be missing during collection
    # though CI should have them.
    sentinel = MagicMock()


class TestSentinel(unittest.TestCase):
    def test_prune_history(self):
        history = [
            {"timestamp": 1000, "value": 10},
            {"timestamp": 500, "value": 20},
        ]
        # Current time 1200. Max age 300.
        # 1000 is 200s old (keep). 500 is 700s old (drop).
        with patch("sentinel.datetime") as mock_dt:
            mock_dt.now.return_value.timestamp.return_value = 1200
            res = sentinel.prune_history(history, 300)
            self.assertEqual(len(res), 1)
            self.assertEqual(res[0]["value"], 10)

    def test_check_drawdown(self):
        # Max in window was 100. Current is 94. Drawdown -0.06.
        # Threshold -0.05. Should trigger.
        history = [{"timestamp": 100, "value": 100}]

        with patch("sentinel.prune_history", return_value=history):
            self.assertTrue(sentinel.check_drawdown(history, 94, -0.05, 3600))
            self.assertFalse(sentinel.check_drawdown(history, 96, -0.05, 3600))

    def test_get_btc_price(self):
        mock_ccxt = MagicMock()
        mock_exchange = MagicMock()
        mock_ccxt.kraken.return_value = mock_exchange
        mock_exchange.fetch_ticker.return_value = {"last": 50000}

        # Patch sys.modules to mock ccxt import inside the function
        with patch.dict(sys.modules, {"ccxt": mock_ccxt}):
            price = sentinel.get_btc_price()
            self.assertEqual(price, 50000)

    def test_send_alert(self):
        mock_requests = MagicMock()
        with (
            patch.dict(sys.modules, {"requests": mock_requests}),
            patch.dict(sentinel.os.environ, {"OPENCLAW_URL": "http://webhook"}),
        ):
            sentinel.send_alert("test")
            mock_requests.post.assert_called_once()
            # Verify timeout is passed
            kwargs = mock_requests.post.call_args[1]
            self.assertIn("timeout", kwargs)

    @patch("sentinel.FtRestClient")
    @patch("sentinel.get_btc_price")
    @patch("sentinel.load_config")
    @patch("sentinel.load_state")
    @patch("sentinel.save_state")
    @patch("sentinel.send_alert")
    @patch("sys.exit")
    @patch("time.sleep")
    def test_main_trigger(
        self,
        mock_sleep,
        mock_exit,
        mock_alert,
        mock_save,
        mock_load,
        mock_config,
        mock_btc,
        mock_client_cls,
    ):
        # Setup
        mock_config.return_value = {"api_server": {"username": "u", "password": "p"}}
        mock_load.return_value = {"balance_history": [], "btc_history": []}

        client_instance = MagicMock()
        mock_client_cls.return_value = client_instance

        # Sequence:
        # 1. Balance 100. No trigger.
        # 2. Balance 90. Trigger (-10%).
        client_instance.balance.side_effect = [{"value": 100}, {"value": 90}]
        client_instance.status.return_value = [{"trade_id": 123}]
        mock_btc.return_value = 50000

        # Mock sys.exit to raise exception so we can catch it
        mock_exit.side_effect = SystemExit

        with self.assertRaises(SystemExit):
            sentinel.main()

        # Verify Alert sent
        mock_alert.assert_called()
        self.assertIn("Drawdown", mock_alert.call_args[0][0])

        # Verify Liquidation
        client_instance.forceexit.assert_called_with(123)

        # Verify Stop
        client_instance.stop.assert_called()


if __name__ == "__main__":
    unittest.main()
