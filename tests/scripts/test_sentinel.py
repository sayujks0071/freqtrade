import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


# Add scripts directory to path
scripts_dir = Path(__file__).resolve().parent.parent.parent / "scripts"
sys.path.append(str(scripts_dir))

# Mock schedule to avoid import error if it wasn't installed in test env (though it should be)
# But we installed it.
from sentinel import Sentinel  # noqa: E402


class TestSentinel(unittest.TestCase):
    def setUp(self):
        self.sentinel = Sentinel()

    @patch("sentinel.requests.post")
    @patch("sentinel.requests.get")
    @patch("sentinel.ccxt.kucoin")
    def test_monitor_normal(self, mock_kucoin, mock_get, mock_post):
        # Setup Mocks
        # Login response
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"access_token": "fake_token"}

        # Balance response
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"total": 1000}

        # BTC Price
        mock_exchange = MagicMock()
        mock_exchange.fetch_ticker.return_value = {"last": 50000}
        mock_kucoin.return_value = mock_exchange

        # Run
        self.sentinel.monitor()

        # Assertions
        # Should have authenticated
        self.assertEqual(self.sentinel.token, "fake_token")
        # History updated
        self.assertEqual(len(self.sentinel.balance_history), 1)
        self.assertEqual(self.sentinel.balance_history[0][1], 1000)
        self.assertEqual(len(self.sentinel.btc_history), 1)
        self.assertEqual(self.sentinel.btc_history[0][1], 50000)

        # Ensure NO emergency actions triggered
        # Filter calls to OPENCLAW_URL or /stopbuy
        emergency_calls = [
            c for c in mock_post.call_args_list
            if "stopbuy" in str(c) or "forceexit" in str(c) or "stop" in str(c)
        ]
        self.assertEqual(len(emergency_calls), 0)

    @patch("sentinel.requests.post")
    @patch("sentinel.requests.get")
    def test_drawdown_trigger(self, mock_get, mock_post):
        # Setup
        self.sentinel.token = "fake_token"

        # Mock API calls
        # 1. First call: High Balance (monitor loop 1)
        # 2. Second call: Low Balance (monitor loop 2)
        # 3. Third call: Get Open Trades (trigger_emergency)
        mock_get.side_effect = [
            MagicMock(status_code=200, json=lambda: {"total": 1000}),
            MagicMock(status_code=200, json=lambda: {"total": 940}),  # 6% drop
            MagicMock(status_code=200, json=lambda: [{"trade_id": 1}, {"trade_id": 2}]),
        ]

        # Mock Post for alerts/actions
        mock_post.return_value.status_code = 200

        # Bypass BTC check for this test by mocking get_btc_price or just let it fail/return None
        with patch("sentinel.get_btc_price", return_value=50000):
            # 1. Run Normal
            self.sentinel.monitor()

            # 2. Run Drawdown
            with self.assertRaises(SystemExit):
                self.sentinel.monitor()

        # Verify Emergency Actions
        # Check calls
        post_urls = [c[0][0] for c in mock_post.call_args_list]
        self.assertTrue(any("stopbuy" in url for url in post_urls))
        self.assertTrue(any("forceexit" in url for url in post_urls))
        self.assertTrue(any("stop" in url for url in post_urls))

        # Verify forceexit called for specific trades
        forceexit_calls = [
            c for c in mock_post.call_args_list
            if "forceexit" in str(c)
        ]
        self.assertEqual(len(forceexit_calls), 2)
        # Check payloads
        payloads = [c[1].get("json") for c in forceexit_calls]
        self.assertIn({"tradeid": 1}, payloads)
        self.assertIn({"tradeid": 2}, payloads)

        # Alert check
        self.assertTrue(any("openclaw" in str(c) for c in mock_post.call_args_list) or
                        any("OPENCLAW" in str(c) for c in mock_post.call_args_list))

    @patch("sentinel.requests.post")
    @patch("sentinel.requests.get")
    @patch("sentinel.ccxt.kucoin")
    def test_btc_drop_trigger(self, mock_kucoin, mock_get, mock_post):
        # Setup
        self.sentinel.token = "fake_token"

        # Balance always stable
        # 1. Balance (Normal)
        # 2. Balance (Drop)
        # 3. Open Trades (Empty list for simplicity)
        mock_get.side_effect = [
            MagicMock(status_code=200, json=lambda: {"total": 1000}),
            MagicMock(status_code=200, json=lambda: {"total": 1000}),
            MagicMock(status_code=200, json=lambda: []),
        ]

        # BTC Price Mocks
        mock_exchange = MagicMock()
        # 1. High Price
        # 2. Low Price (Drop > 10%)
        # 50000 * 0.90 = 45000. So 44000 is > 10% drop.
        mock_exchange.fetch_ticker.side_effect = [
            {"last": 50000},
            {"last": 44000},
        ]
        mock_kucoin.return_value = mock_exchange

        mock_post.return_value.status_code = 200

        # 1. Run Normal
        self.sentinel.monitor()

        # 2. Run BTC Drop
        with self.assertRaises(SystemExit):
            self.sentinel.monitor()

        # Verify Emergency Actions
        post_urls = [c[0][0] for c in mock_post.call_args_list]
        self.assertTrue(any("stopbuy" in url for url in post_urls))
        self.assertTrue(any("stop" in url for url in post_urls))


if __name__ == "__main__":
    unittest.main()
