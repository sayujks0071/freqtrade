import json
from unittest.mock import MagicMock, patch

import pytest

from scripts.sentinel import Sentinel


@pytest.fixture
def mock_config(tmp_path):
    config = {
        "api_server": {
            "listen_ip_address": "127.0.0.1",
            "listen_port": 8080,
            "username": "user",
            "password": "password"
        }
    }
    config_file = tmp_path / "config.json"
    with config_file.open("w") as f:
        json.dump(config, f)
    return config_file


@pytest.fixture
def mock_sentinel(mock_config):
    with patch("scripts.sentinel.ccxt") as mock_ccxt:
        mock_exchange = MagicMock()
        mock_ccxt.kraken.return_value = mock_exchange
        mock_exchange.markets = {"BTC/USD": {}}  # Mock markets loaded

        # Mock requests
        with patch("scripts.sentinel.requests.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session

            # Mock state file loading (empty initially)
            with patch("scripts.sentinel.Sentinel.load_state", return_value=[]):
                # Mock state persistence to avoid file writes
                with patch("scripts.sentinel.Sentinel.save_state"):
                    sentinel = Sentinel(
                        mock_config,
                        panic_sell=True,
                        openclaw_url="http://openclaw",
                        dry_run=False
                    )
                    sentinel.exchange = mock_exchange
                    sentinel.session = mock_session
                    return sentinel


def test_initialization(mock_sentinel):
    assert mock_sentinel.api_base == "http://127.0.0.1:8080/api/v1"
    assert mock_sentinel.panic_sell is True


def test_login(mock_sentinel):
    mock_sentinel.session.get.return_value.status_code = 401
    mock_sentinel.session.post.return_value.status_code = 200
    mock_sentinel.session.post.return_value.json.return_value = {"access_token": "token123"}

    mock_sentinel.login()

    mock_sentinel.session.post.assert_called_with(
        "http://127.0.0.1:8080/api/v1/token/login",
        auth=("user", "password"),
        timeout=10
    )
    assert mock_sentinel.jwt_token == "token123"


def test_check_drawdown_no_data(mock_sentinel):
    mock_sentinel.get_balance_total = MagicMock(return_value=None)
    assert mock_sentinel.check_drawdown() is False


def test_check_drawdown_ok(mock_sentinel):
    mock_sentinel.get_balance_total = MagicMock(return_value=100.0)
    mock_sentinel.state = []

    # First call, max=100
    assert mock_sentinel.check_drawdown() is False
    assert len(mock_sentinel.state) == 1

    # Second call, balance 96 (4% drop), max=100 -> 4% drawdown -> False
    mock_sentinel.get_balance_total.return_value = 96.0
    assert mock_sentinel.check_drawdown() is False

    # Third call, balance 94 (6% drop), max=100 -> 6% drawdown -> True
    mock_sentinel.get_balance_total.return_value = 94.0
    assert mock_sentinel.check_drawdown() is True


def test_check_btc_crash(mock_sentinel):
    # Mock OHLCV: [timestamp, open, high, low, close, volume]
    # Highs: 50000, 50000, 50000, 50000.
    # Last close: 44000 (12% drop from 50000)
    mock_ohlcv = [
        [1, 49000, 50000, 48000, 49000, 100],
        [2, 49000, 49500, 48000, 49000, 100],
        [3, 49000, 49000, 48000, 49000, 100],
        [4, 49000, 49000, 48000, 49000, 100],
        [5, 49000, 49000, 44000, 44000, 100],  # Current
    ]
    mock_sentinel.exchange.fetch_ohlcv.return_value = mock_ohlcv

    assert mock_sentinel.check_btc_crash() is True

    # Test safe case
    mock_ohlcv[-1][4] = 48000  # 4% drop
    assert mock_sentinel.check_btc_crash() is False


def test_trigger_emergency(mock_sentinel):
    with patch("scripts.sentinel.requests.post") as mock_post:
        # Mock status response for liquidation
        mock_sentinel.session.get.return_value.status_code = 200
        mock_sentinel.session.get.return_value.json.return_value = [
            {"trade_id": 1, "pair": "ETH/USDT"}
        ]
        mock_sentinel.session.post.return_value.status_code = 200

        mock_sentinel.trigger_emergency("Test Reason")

        # Alert sent
        mock_post.assert_called_with(
            "http://openclaw",
            json={
                "message": "CRITICAL ALERT: Test Reason. Triggering Circuit Breaker.",
                "text": "CRITICAL ALERT: Test Reason. Triggering Circuit Breaker."
            },
            timeout=10
        )

        # Stop called
        mock_sentinel.session.post.assert_any_call(
            "http://127.0.0.1:8080/api/v1/stop",
            timeout=10
        )

        # Panic sell called (since enabled in fixture)
        mock_sentinel.session.post.assert_any_call(
            "http://127.0.0.1:8080/api/v1/forceexit",
            json={"tradeid": 1},
            timeout=10
        )


def test_trigger_emergency_dry_run(mock_sentinel):
    mock_sentinel.dry_run = True
    with patch("scripts.sentinel.requests.post") as mock_post:
        mock_sentinel.trigger_emergency("Test Reason")

        # Alert sent
        mock_post.assert_called()

        # Stop NOT called (session.post mock)
        # Note: We are using the mock_session from fixture, which has post mocked
        assert mock_sentinel.session.post.call_count == 0
