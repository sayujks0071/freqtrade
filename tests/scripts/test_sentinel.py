import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests


# Add scripts directory to sys.path to import sentinel
# Using the strategy pattern from memory: Path(__file__).resolve()....
sys.path.append(str(Path(__file__).resolve().parent.parent.parent / "scripts"))


@pytest.fixture
def mock_config_path(tmp_path):
    config_file = tmp_path / "config.json"
    config_data = {
        "api_server": {
            "listen_ip_address": "127.0.0.1",
            "listen_port": 8080,
            "username": "user",
            "password": "password",
        }
    }
    with config_file.open("w") as f:
        json.dump(config_data, f)
    return config_file


@pytest.fixture
def sentinel(mock_config_path):
    from sentinel import Sentinel

    # Patch ccxt.binance at import time or initialization
    with patch("ccxt.binance"):
        s = Sentinel(mock_config_path, interval=1, openclaw_url="http://openclaw", dry_run=True)
        # Mock exchange instance explicitly
        s.exchange = MagicMock()
        return s


def test_login_success(sentinel):
    with patch("requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"access_token": "token123"}

        assert sentinel._login() is True
        assert sentinel.auth_token == "token123"


def test_login_failure(sentinel):
    with patch("requests.post") as mock_post:
        mock_post.side_effect = requests.RequestException("Connection Error")
        assert sentinel._login() is False


def test_rpc_get(sentinel):
    sentinel.auth_token = "token123"
    with patch("requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"total": 1000}

        result = sentinel._rpc_get("balance")
        assert result == {"total": 1000}
        mock_get.assert_called_with(
            "http://127.0.0.1:8080/api/v1/balance",
            headers={"Authorization": "Bearer token123"},
            timeout=10,
        )


def test_btc_drop_calculation(sentinel):
    # OHLCV format: [timestamp, open, high, low, close, volume]
    # Scenario: High was 100, now 89 (11% drop)

    # 5 candles:
    # 1. High 100, Close 99
    # 2. High 99, Close 98
    # 3. High 98, Close 95
    # 4. High 95, Close 90
    # 5. High 90, Close 89

    ohlcv = [
        [1, 99, 100, 99, 99, 10],
        [2, 99, 99, 98, 98, 10],
        [3, 98, 98, 95, 95, 10],
        [4, 95, 95, 90, 90, 10],
        [5, 90, 90, 89, 89, 10],
    ]

    sentinel.exchange.fetch_ohlcv.return_value = ohlcv

    drop = sentinel.get_btc_drop_4h()
    # Max High = 100
    # Current Close = 89
    # Drop = (100 - 89) / 100 = 0.11
    assert drop == 0.11


def test_drawdown_calculation(sentinel):
    # Add history
    now = datetime.now(timezone.utc)  # noqa: UP017
    # 40 mins ago: 1000
    sentinel.balance_history.append((now - timedelta(minutes=40), 1000.0))
    # 20 mins ago: 1050 (Peak)
    sentinel.balance_history.append((now - timedelta(minutes=20), 1050.0))
    # Now: 900
    current_balance = 900.0

    drawdown = sentinel.get_drawdown_1h(current_balance)
    # Peak = 1050
    # Current = 900
    # Drawdown = (1050 - 900) / 1050 = 150 / 1050 = 0.142857...
    assert drawdown == pytest.approx(0.142857, abs=1e-4)


def test_trigger_emergency_dry_run(sentinel):
    # Dry run mode
    sentinel.dry_run = True

    with (
        patch.object(sentinel, "notify_openclaw") as mock_notify,
        patch.object(sentinel, "_rpc_post") as mock_rpc,
    ):
        sentinel.trigger_emergency("Test Reason")

        mock_notify.assert_called_once()
        # In dry run, rpc calls should NOT happen
        mock_rpc.assert_not_called()


def test_trigger_emergency_live(sentinel):
    sentinel.dry_run = False

    with (
        patch.object(sentinel, "notify_openclaw") as mock_notify,
        patch.object(sentinel, "_rpc_post") as mock_rpc,
        pytest.raises(SystemExit),
    ):  # Should exit
        sentinel.trigger_emergency("Test Reason")

        mock_notify.assert_called_once()
        # Should call forceexit and stop
        assert mock_rpc.call_count == 2
        mock_rpc.assert_any_call("forceexit")
        mock_rpc.assert_any_call("stop")
