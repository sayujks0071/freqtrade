import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# Add scripts directory to path to import sentinel
sys.path.append(str(Path(__file__).parent.parent.parent / "scripts"))
from sentinel import Sentinel  # noqa: E402, RUF100


@pytest.fixture
def mock_config(tmp_path):
    config_path = tmp_path / "config.json"
    config_data = {
        "api_server": {
            "listen_ip_address": "127.0.0.1",
            "listen_port": 8080,
            "username": "testuser",
            "password": "testpassword",
        }
    }
    with config_path.open("w") as f:
        json.dump(config_data, f)
    return config_path


@pytest.fixture
def sentinel(mock_config):
    with patch("sentinel.Sentinel._load_state", return_value=[]):
        s = Sentinel(mock_config)
        # Mock API URL to avoid issues
        s.api_url = "http://mock_url"
        # Mock state file to tmp
        s.state_file = mock_config.parent / "sentinel_state.json"
        return s


def test_login(sentinel):
    with patch("requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "access_token": "access123",
            "refresh_token": "refresh123",
        }
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        sentinel.login()

        assert sentinel.access_token == "access123"
        assert sentinel.refresh_token == "refresh123"
        mock_post.assert_called_once()


def test_api_request_refresh(sentinel):
    """Test that api_request refreshes token on 401"""
    sentinel.access_token = "old_token"
    sentinel.refresh_token = "refresh_token"

    with (
        patch("requests.request") as mock_request,
        patch("requests.post") as mock_post,
    ):
        # First request fails with 401
        response_401 = MagicMock()
        response_401.status_code = 401

        # Second request (retry) succeeds
        response_200 = MagicMock()
        response_200.status_code = 200
        response_200.json.return_value = {"success": True}

        # Side effect for requests.request
        mock_request.side_effect = [response_401, response_200]

        # Mock refresh call
        refresh_response = MagicMock()
        refresh_response.status_code = 200
        refresh_response.json.return_value = {"access_token": "new_token"}
        mock_post.return_value = refresh_response

        data = sentinel.api_request("GET", "/endpoint")

        assert data == {"success": True}
        assert sentinel.access_token == "new_token"
        assert mock_request.call_count == 2


def test_check_drawdown_trigger(sentinel):
    # Mock trigger_emergency
    sentinel.trigger_emergency = MagicMock()

    # Mock time to control flow
    base_time = 1000000.0

    # 1. First check: Balance 100
    with (
        patch("sentinel.Sentinel.get_total_balance", return_value=100.0),
        patch("time.time", return_value=base_time),
    ):
        sentinel.check_drawdown()

    assert not sentinel.trigger_emergency.called
    assert len(sentinel.balance_history) == 1
    assert sentinel.balance_history[0][1] == 100.0

    # 2. Second check: Balance 96 (4% drop) - No trigger
    with (
        patch("sentinel.Sentinel.get_total_balance", return_value=96.0),
        patch("time.time", return_value=base_time + 300),
    ):
        sentinel.check_drawdown()

    assert not sentinel.trigger_emergency.called

    # 3. Third check: Balance 94 (6% drop from max 100) - Trigger
    with (
        patch("sentinel.Sentinel.get_total_balance", return_value=94.0),
        patch("time.time", return_value=base_time + 600),
    ):
        sentinel.check_drawdown()

    assert sentinel.trigger_emergency.called


def test_check_btc_crash_trigger(sentinel):
    sentinel.trigger_emergency = MagicMock()

    # Mock ccxt
    mock_exchange = MagicMock()
    with patch("ccxt.gateio", return_value=mock_exchange):
        # 5 candles: [ts, open, high, low, close, vol]
        # Max high = 100
        # Current close (last candle) = 89 (11% drop)
        candles = [
            [0, 100, 100, 99, 99, 10],  # T-4
            [0, 99, 99, 98, 98, 10],  # T-3
            [0, 98, 98, 97, 97, 10],  # T-2
            [0, 97, 97, 95, 95, 10],  # T-1
            [0, 95, 95, 89, 89, 10],  # T-0 (Current)
        ]
        mock_exchange.fetch_ohlcv.return_value = candles

        sentinel.check_btc_crash()

        assert sentinel.trigger_emergency.called
        assert "Bitcoin Crash Alert" in sentinel.trigger_emergency.call_args[0][0]


def test_trigger_emergency_calls_api(sentinel):
    sentinel.api_request = MagicMock()

    sentinel.trigger_emergency("Test Reason")

    # Check calls
    # 1. Force Exit
    sentinel.api_request.assert_any_call("POST", "/forceexit", json={"tradeid": "all"})
    # 2. Stop
    sentinel.api_request.assert_any_call("POST", "/stop")
