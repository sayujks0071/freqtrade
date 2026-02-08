import sys
import unittest
from pathlib import Path
from unittest.mock import patch


# Ensure scripts directory is in path
sys.path.append(str(Path(__file__).resolve().parent.parent.parent / "scripts"))

from sentinel import Sentinel  # noqa: E402, RUF100


class TestSentinel(unittest.TestCase):
    @patch("sentinel.ccxt.binance")
    def test_init_default(self, mock_binance):
        sentinel = Sentinel()
        self.assertEqual(sentinel.api_url, "http://127.0.0.1:8080")
        mock_binance.assert_called_once()

    @patch("sentinel.ccxt.binance")
    @patch(
        "builtins.open",
        new_callable=unittest.mock.mock_open,
        read_data=(
            '{"api_server": {"listen_ip_address": "0.0.0.0", '
            '"listen_port": 1234, "username": "user", "password": "pass"}}'
        ),
    )
    def test_init_with_config(self, mock_file, mock_binance):
        sentinel = Sentinel(config_path="config.json")
        self.assertEqual(sentinel.api_url, "http://127.0.0.1:1234")
        self.assertEqual(sentinel.api_username, "user")
        self.assertEqual(sentinel.api_password, "pass")

    @patch("sentinel.ccxt.binance")
    def test_check_market_crash_no_crash(self, mock_binance):
        sentinel = Sentinel()
        # Mock OHLCV: [timestamp, open, high, low, close, volume]
        # Max high = 105, Current close = 100. Drop = 5/105 < 10%
        mock_ohlcv = [
            [1000, 100, 105, 95, 100, 10],
            [2000, 100, 102, 98, 100, 10],
            [3000, 100, 101, 99, 100, 10],
            [4000, 100, 100, 95, 100, 10],
            [5000, 100, 100, 90, 100, 10],
        ]
        sentinel.exchange.fetch_ohlcv.return_value = mock_ohlcv

        self.assertFalse(sentinel.check_market_crash())

    @patch("sentinel.ccxt.binance")
    def test_check_market_crash_crash(self, mock_binance):
        sentinel = Sentinel()
        # Max high = 120, Current close = 100. Drop = 20/120 > 10%
        mock_ohlcv = [
            [1000, 110, 120, 105, 115, 10],
            [2000, 115, 118, 110, 112, 10],
            [3000, 112, 115, 108, 110, 10],
            [4000, 110, 112, 100, 105, 10],
            [5000, 105, 108, 90, 100, 10],
        ]
        sentinel.exchange.fetch_ohlcv.return_value = mock_ohlcv

        self.assertTrue(sentinel.check_market_crash())

    @patch("sentinel.requests.get")
    @patch("sentinel.ccxt.binance")
    def test_check_portfolio_drawdown_no_drawdown(self, mock_binance, mock_get):
        sentinel = Sentinel()

        # Mock API response
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"total": 1000}

        # First check, history empty -> no drawdown
        self.assertFalse(sentinel.check_portfolio_drawdown())

        # Second check, value same -> no drawdown
        self.assertFalse(sentinel.check_portfolio_drawdown())

    @patch("sentinel.requests.get")
    @patch("sentinel.ccxt.binance")
    def test_check_portfolio_drawdown_drawdown(self, mock_binance, mock_get):
        sentinel = Sentinel()

        # 1. First check: Balance 1000
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"total": 1000}
        sentinel.check_portfolio_drawdown()

        # 2. Second check: Balance 900 (10% drop from 1000)
        mock_get.return_value.json.return_value = {"total": 900}

        self.assertTrue(sentinel.check_portfolio_drawdown())

    @patch("sentinel.time.sleep")
    @patch("sentinel.requests.post")
    @patch("sentinel.requests.get")
    @patch("sentinel.sys.exit")
    @patch("sentinel.ccxt.binance")
    def test_trigger_emergency(self, mock_binance, mock_exit, mock_get, mock_post, mock_sleep):
        sentinel = Sentinel()
        sentinel.openclaw_url = "http://openclaw.test"

        # Mock /status for force exit
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = [{"trade_id": 1}, {"trade_id": 2}]

        try:
            sentinel.trigger_emergency("Test Reason")
        except Exception:
            pass  # catch exit

        # Check OpenClaw alert
        mock_post.assert_any_call(
            "http://openclaw.test",
            json={
                "message": (
                    "CRITICAL ALERT: Sentinel triggered due to Test Reason. "
                    "Engaging Emergency Protocol."
                ),
                "token": None,
            },
            timeout=5,
        )

        # Check stopbuy
        mock_post.assert_any_call(
            "http://127.0.0.1:8080/api/v1/stopbuy",
            auth=("freqtrader", "SuperSecurePassword123!"),
            timeout=10,
        )

        # Check forceexit loop
        mock_post.assert_any_call(
            "http://127.0.0.1:8080/api/v1/forceexit",
            json={"tradeid": 1},
            auth=("freqtrader", "SuperSecurePassword123!"),
            timeout=10,
        )
        mock_post.assert_any_call(
            "http://127.0.0.1:8080/api/v1/forceexit",
            json={"tradeid": 2},
            auth=("freqtrader", "SuperSecurePassword123!"),
            timeout=10,
        )

        # Check stop
        mock_post.assert_any_call(
            "http://127.0.0.1:8080/api/v1/stop",
            auth=("freqtrader", "SuperSecurePassword123!"),
            timeout=10,
        )

        # Check sleep
        mock_sleep.assert_called_with(5)

        # Check exit
        mock_exit.assert_called_with(1)
