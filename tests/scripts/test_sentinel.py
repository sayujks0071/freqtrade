import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
import requests_mock


# Add scripts directory to path
# __file__ is tests/scripts/test_sentinel.py
# parent -> tests/scripts
# parent.parent -> tests
# parent.parent.parent -> root
# root / scripts
sys.path.append(str(Path(__file__).resolve().parent.parent.parent / "scripts"))

from sentinel import Sentinel


@pytest.fixture
def mock_config(tmp_path):
    config_file = tmp_path / "config.json"
    config_content = {
        "api_server": {
            "enabled": True,
            "listen_ip_address": "127.0.0.1",
            "listen_port": 8080,
            "username": "user",
            "password": "password",
        }
    }
    with config_file.open("w") as f:
        json.dump(config_content, f)
    return config_file


@pytest.fixture
def sentinel(mock_config):
    with requests_mock.Mocker() as m:
        # Mock login
        m.post("http://127.0.0.1:8080/api/v1/token/login", json={"access_token": "token"})

        # We need to mock ccxt.gateio too
        with patch("ccxt.gateio") as mock_ccxt:
            s = Sentinel(mock_config)
            s.btc_exchange = mock_ccxt.return_value
            return s


def test_init_and_auth(mock_config):
    with requests_mock.Mocker() as m:
        m.post("http://127.0.0.1:8080/api/v1/token/login", json={"access_token": "token"})
        with patch("ccxt.gateio"):
            s = Sentinel(mock_config)
            assert s.rpc_token == "token"
            assert s.rpc_url == "http://127.0.0.1:8080/api/v1"


def test_check_drawdown_no_history(sentinel):
    with requests_mock.Mocker() as m:
        m.get("http://127.0.0.1:8080/api/v1/balance", json={"total": 1000})
        assert sentinel.check_drawdown() is False
        assert len(sentinel.balance_history) == 1


def test_check_drawdown_trigger(sentinel):
    # Pre-fill history with a high balance
    now = datetime.now()
    sentinel.balance_history = [(now - timedelta(minutes=30), 1000.0)]

    # Mock current balance significantly lower (e.g. 900, which is >5% drop from 1000)
    with requests_mock.Mocker() as m:
        m.get("http://127.0.0.1:8080/api/v1/balance", json={"total": 900.0})

        triggered = sentinel.check_drawdown()
        assert triggered is True


def test_check_drawdown_no_trigger_small_drop(sentinel):
    now = datetime.now()
    sentinel.balance_history = [(now - timedelta(minutes=30), 1000.0)]

    # Drop only 1%
    with requests_mock.Mocker() as m:
        m.get("http://127.0.0.1:8080/api/v1/balance", json={"total": 990.0})

        triggered = sentinel.check_drawdown()
        assert triggered is False


def test_check_btc_drop_trigger(sentinel):
    # ohlcv: [timestamp, open, high, low, close, volume]
    # Max high: 50000. Current close: 40000 (20% drop)
    sentinel.btc_exchange.fetch_ohlcv.return_value = [
        [1000, 50000, 50000, 49000, 49500, 100],
        [2000, 49500, 49600, 48000, 48500, 100],
        [3000, 48500, 48500, 40000, 40000, 100],
    ]

    assert sentinel.check_btc_drop() is True


def test_check_btc_drop_no_trigger(sentinel):
    # Max high: 50000. Current close: 48000 (4% drop)
    sentinel.btc_exchange.fetch_ohlcv.return_value = [
        [1000, 50000, 50000, 49000, 49500, 100],
        [2000, 49500, 49600, 48000, 48500, 100],
        [3000, 48500, 48500, 47000, 48000, 100],
    ]

    assert sentinel.check_btc_drop() is False


def test_emergency_actions(sentinel):
    with requests_mock.Mocker() as m:
        m.post("http://127.0.0.1:8080/api/v1/forceexit", status_code=200)
        m.post("http://127.0.0.1:8080/api/v1/stop", status_code=200)

        sentinel.trigger_emergency("Test Reason")

        # Check call count. We have 2 POST requests.
        assert m.call_count == 2
        history = m.request_history
        # Order matters based on implementation: alert (logging), liquidation, kill_switch
        assert "forceexit" in history[0].url
        assert "stop" in history[1].url
