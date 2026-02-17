import json
import sys
from datetime import UTC
from pathlib import Path
from unittest.mock import mock_open, patch

import pytest


# Ensure scripts module can be imported
sys.path.append(str(Path(__file__).parent.parent))

from scripts.sentinel import Sentinel  # noqa: E402, RUF100


# Mock config
MOCK_CONFIG = {
    "api_server": {
        "listen_ip_address": "127.0.0.1",
        "listen_port": 8080,
        "username": "user",
        "password": "password",
    }
}


@pytest.fixture
def mock_sentinel():
    with (
        patch("scripts.sentinel.json.load", return_value=MOCK_CONFIG),
        patch("scripts.sentinel.Path.exists", return_value=True),
        patch("scripts.sentinel.Path.open", mock_open(read_data=json.dumps(MOCK_CONFIG))),
        patch("scripts.sentinel.ccxt.kraken") as mock_kraken,
    ):
        sentinel = Sentinel("config.json", panic_sell=False, openclaw_url=None)
        sentinel.exchange = mock_kraken.return_value
        # Mock fetch_ohlcv to return valid data by default
        sentinel.exchange.fetch_ohlcv.return_value = []
        sentinel.exchange.fetch_ticker.return_value = {"last": 100}
        return sentinel


def test_init(mock_sentinel):
    assert mock_sentinel.api_url == "http://127.0.0.1:8080/api/v1"
    assert mock_sentinel.panic_sell_enabled is False


@patch("requests.post")
def test_authenticate(mock_post, mock_sentinel):
    mock_post.return_value.json.return_value = {"access_token": "token123"}
    mock_post.return_value.raise_for_status.return_value = None

    mock_sentinel.authenticate()

    assert mock_sentinel.auth_token == "token123"
    assert mock_sentinel.headers["Authorization"] == "Bearer token123"


def test_check_btc_crash_no_crash(mock_sentinel):
    # Mock OHLCV: Price stable
    # [timestamp, open, high, low, close, volume]
    mock_sentinel.exchange.fetch_ohlcv.return_value = [
        [0, 100, 100, 90, 95, 1],
        [0, 95, 98, 92, 95, 1],
        [0, 95, 97, 94, 96, 1],
        [0, 96, 99, 95, 98, 1],
        [0, 98, 98, 97, 98, 1],
    ]
    mock_sentinel.exchange.fetch_ticker.return_value = {"last": 98}

    assert mock_sentinel.check_btc_crash() is False


def test_check_btc_crash_triggered(mock_sentinel):
    # Max High was 100. Current is 85 (15% drop).
    mock_sentinel.exchange.fetch_ohlcv.return_value = [
        [0, 100, 100, 90, 95, 1],
        [0, 95, 95, 90, 90, 1],
        [0, 90, 90, 85, 85, 1],
        [0, 85, 85, 80, 80, 1],
        [0, 80, 80, 75, 75, 1],
    ]
    mock_sentinel.exchange.fetch_ticker.return_value = {"last": 85}

    # Max High = 100. Drop = (85 - 100) / 100 = -0.15
    assert mock_sentinel.check_btc_crash() is True


@patch("requests.get")
def test_check_drawdown_no_drawdown(mock_get, mock_sentinel):
    mock_get.return_value.json.return_value = {"total": 1000}
    # Mock state with recent balance
    mock_sentinel.state = {"balance_history": [{"timestamp": 0, "balance": 1000}]}

    assert mock_sentinel.check_drawdown() is False


@patch("requests.get")
def test_check_drawdown_triggered(mock_get, mock_sentinel):
    mock_get.return_value.json.return_value = {"total": 900}

    # Mock datetime to ensure history is kept
    with patch("scripts.sentinel.datetime") as mock_dt:
        mock_dt.now.return_value.timestamp.return_value = 10000
        # Use datetime.UTC directly for mocking
        mock_dt.UTC = UTC

        # History entry within last hour (10000 - 3600 = 6400)
        mock_sentinel.state = {"balance_history": [{"timestamp": 9000, "balance": 1000}]}

        assert mock_sentinel.check_drawdown() is True


@patch("requests.post")
@patch("sys.exit")
def test_trigger_emergency(mock_exit, mock_post, mock_sentinel):
    mock_sentinel.openclaw_url = "http://webhook"
    mock_sentinel.panic_sell_enabled = True

    # Mock status for panic sell
    with patch("requests.get") as mock_get:
        mock_get.return_value.json.return_value = [{"trade_id": 1, "pair": "BTC/USDT"}]

        mock_sentinel.trigger_emergency("Test")

        # Verify Alert
        mock_post.assert_any_call(
            "http://webhook", json={"message": "CRITICAL ALERT: Test"}, timeout=5
        )

        # Verify Panic Sell
        mock_post.assert_any_call(
            f"{mock_sentinel.api_url}/forceexit",
            headers={},
            json={"tradeid": 1},
            timeout=5,
        )

        # Verify Stop
        mock_post.assert_any_call(f"{mock_sentinel.api_url}/stop", headers={}, timeout=5)

        # Verify Exit
        mock_exit.assert_called_with(0)
