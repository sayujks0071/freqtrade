import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add scripts directory to path to import sentinel
sys.path.append(
    str(Path(__file__).resolve().parent.parent.parent / "scripts")
)  # noqa: E402

from sentinel import Sentinel  # noqa: E402


class TestSentinel(unittest.TestCase):
    def setUp(self):
        self.rpc_url = "http://localhost:8080/api/v1"
        self.rpc_user = "user"
        self.rpc_pass = "pass"
        self.webhook = "http://webhook"

        # Patch ccxt and requests
        self.ccxt_patcher = patch("sentinel.ccxt.gateio")
        self.mock_ccxt_class = self.ccxt_patcher.start()
        self.mock_exchange = self.mock_ccxt_class.return_value

        self.requests_get_patcher = patch("sentinel.requests.get")
        self.mock_get = self.requests_get_patcher.start()

        self.requests_post_patcher = patch("sentinel.requests.post")
        self.mock_post = self.requests_post_patcher.start()

        self.sentinel = Sentinel(
            self.rpc_url,
            self.rpc_user,
            self.rpc_pass,
            self.webhook,
            check_interval=1,
        )

    def tearDown(self):
        self.ccxt_patcher.stop()
        self.requests_get_patcher.stop()
        self.requests_post_patcher.stop()

    def test_initial_state(self):
        self.assertFalse(self.sentinel.tripped)
        self.assertEqual(len(self.sentinel.balance_history), 0)

    def test_update_history(self):
        self.sentinel.update_history(1000, 50000)
        self.assertEqual(len(self.sentinel.balance_history), 1)
        self.assertEqual(self.sentinel.balance_history[0][1], 1000)
        self.assertEqual(self.sentinel.price_history[0][1], 50000)

    def test_drawdown_check_no_drawdown(self):
        # 1000 -> 1000 -> 1000
        self.sentinel.update_history(1000, 50000)
        is_dd, val = self.sentinel.check_drawdown()
        self.assertFalse(is_dd)
        self.assertEqual(val, 0.0)

    def test_drawdown_check_trigger(self):
        # 1000 -> 900 (10% drop)
        self.sentinel.update_history(1000, 50000)
        self.sentinel.update_history(900, 50000)

        is_dd, val = self.sentinel.check_drawdown()
        self.assertTrue(is_dd)
        self.assertAlmostEqual(val, -0.10)

    def test_crash_check_no_crash(self):
        self.sentinel.update_history(1000, 50000)
        is_crash, _ = self.sentinel.check_crash()
        self.assertFalse(is_crash)

    def test_crash_check_trigger(self):
        # 50000 -> 40000 (20% drop)
        self.sentinel.update_history(1000, 50000)
        self.sentinel.update_history(1000, 40000)

        is_crash, val = self.sentinel.check_crash()
        self.assertTrue(is_crash)
        self.assertAlmostEqual(val, -0.20)

    def test_trigger_emergency(self):
        self.sentinel.trigger_emergency("Test Reason")

        self.assertTrue(self.sentinel.tripped)

        # Verify RPC calls
        self.mock_post.assert_any_call(
            f"{self.rpc_url}/stop", auth=(self.rpc_user, self.rpc_pass), timeout=10
        )
        self.mock_post.assert_any_call(
            f"{self.rpc_url}/forceexit",
            auth=(self.rpc_user, self.rpc_pass),
            timeout=10,
        )

        # Verify Webhook
        self.mock_post.assert_any_call(
            self.webhook, json={"content": "CRITICAL ALERT: Test Reason"}, timeout=10
        )

    def test_run_loop_drawdown(self):
        # Setup mock returns
        # Iteration 1: Balance 1000, Price 50000
        # Iteration 2: Balance 900, Price 50000 -> Trigger Drawdown

        self.mock_get.side_effect = [
            MagicMock(status_code=200, json=lambda: {"total": 1000}),
            MagicMock(status_code=200, json=lambda: {"total": 900}),
        ]

        self.mock_exchange.fetch_ticker.side_effect = [
            {"last": 50000},
            {"last": 50000},
        ]

        # We need to run sentinel.run(), but break the loop when tripped.
        # run() loops while not tripped.

        # To avoid infinite loop in case of failure, run in a separate thread
        # or just trust the logic.
        # Since tripped is checked in loop, it should exit after 2nd iteration.

        # We need to ensure sleep doesn't actually sleep long
        with patch("time.sleep", return_value=None):
            self.sentinel.run()

        self.assertTrue(self.sentinel.tripped)
        self.mock_post.assert_any_call(
            self.webhook,
            json={"content": "CRITICAL ALERT: Drawdown > 5% (-10.00%)"},
            timeout=10,
        )

    def test_run_loop_crash(self):
        # Setup mock returns
        # Iteration 1: Balance 1000, Price 50000
        # Iteration 2: Balance 1000, Price 40000 -> Trigger Crash

        self.mock_get.side_effect = [
            MagicMock(status_code=200, json=lambda: {"total": 1000}),
            MagicMock(status_code=200, json=lambda: {"total": 1000}),
        ]

        self.mock_exchange.fetch_ticker.side_effect = [
            {"last": 50000},
            {"last": 40000},
        ]

        with patch("time.sleep", return_value=None):
            self.sentinel.run()

        self.assertTrue(self.sentinel.tripped)
        self.mock_post.assert_any_call(
            self.webhook,
            json={"content": "CRITICAL ALERT: Bitcoin Drop > 10% (-20.00%)"},
            timeout=10,
        )


if __name__ == "__main__":
    unittest.main()
