import time
from unittest.mock import MagicMock, patch

import pytest

from scripts.sentinel import FreqtradeClient, Sentinel


@pytest.fixture
def mock_freqtrade_client():
    with patch("scripts.sentinel.FreqtradeClient") as MockClient:
        client = MockClient.return_value
        client.get_balance.return_value = {"total": 1000.0}
        client.stop_bot.return_value = {"status": "stopped"}
        yield client


@pytest.fixture
def mock_market_data():
    with patch("scripts.sentinel.MarketData") as MockMarket:
        market = MockMarket.return_value
        market.get_price_drop.return_value = 0.0
        yield market


@pytest.fixture
def sentinel(mock_freqtrade_client, mock_market_data):
    # Mock state file to avoid file I/O
    with patch("scripts.sentinel.STATE_FILE") as mock_file:
        mock_file.exists.return_value = False

        # Instantiate Sentinel
        s = Sentinel()
        # Ensure our fixtures are the ones used
        s.ft_client = mock_freqtrade_client
        s.market = mock_market_data

        # Reset state
        s.state = {"balance_history": [], "triggered": False}
        return s


def test_drawdown_trigger(sentinel):
    # Simulate history with high balance
    sentinel.state["balance_history"] = [
        {"ts": time.time() - 1800, "balance": 1000.0}  # 30 mins ago
    ]

    # Current balance drops significantly (e.g. 900, which is 10% drop)
    sentinel.ft_client.get_balance.return_value = {"total": 900.0}

    sentinel.run_check()

    # Verify Kill Switch was called
    sentinel.ft_client.kill_switch.assert_called_once()
    assert sentinel.state["triggered"] is True


def test_btc_drop_trigger(sentinel):
    # Balance is fine
    sentinel.ft_client.get_balance.return_value = {"total": 1000.0}

    # BTC drops 15%
    sentinel.market.get_price_drop.return_value = 15.0

    sentinel.run_check()

    # Verify Kill Switch was called
    sentinel.ft_client.kill_switch.assert_called_once()
    assert sentinel.state["triggered"] is True


def test_no_trigger_normal_conditions(sentinel):
    # Balance stable
    sentinel.state["balance_history"] = [{"ts": time.time() - 1800, "balance": 1000.0}]
    sentinel.ft_client.get_balance.return_value = {"total": 990.0}  # 1% drop

    # BTC stable
    sentinel.market.get_price_drop.return_value = 2.0

    sentinel.run_check()

    # Verify Kill Switch NOT called
    sentinel.ft_client.kill_switch.assert_not_called()
    assert sentinel.state["triggered"] is False


def test_already_triggered(sentinel):
    sentinel.state["triggered"] = True

    sentinel.run_check()

    # Should exit immediately without checking API
    sentinel.ft_client.get_balance.assert_not_called()
    sentinel.market.get_price_drop.assert_not_called()


def test_balance_history_update(sentinel):
    # Test that balance is added to history
    sentinel.ft_client.get_balance.return_value = {"total": 1050.0}

    sentinel.run_check()

    history = sentinel.state["balance_history"]
    assert len(history) == 1
    assert history[0]["balance"] == 1050.0


# ---------------------------------------------------------------------------
# FreqtradeClient Tests (JWT Auth)
# ---------------------------------------------------------------------------


def test_freqtrade_client_login():
    with patch("scripts.sentinel.requests.Session") as MockSession:
        session_instance = MockSession.return_value
        # Mock login response
        login_resp = MagicMock()
        login_resp.status_code = 200
        login_resp.json.return_value = {"access_token": "test_token"}
        session_instance.post.return_value = login_resp

        client = FreqtradeClient("http://test", "user", "pass")
        assert client.login() is True
        assert client.access_token == "test_token"

        session_instance.post.assert_called_with(
            "http://test/api/v1/token/login",
            data={"username": "user", "password": "pass"},
            timeout=10,
        )


def test_freqtrade_client_request_with_token():
    with patch("scripts.sentinel.requests.Session") as MockSession:
        session_instance = MockSession.return_value

        # Mock successful API response
        api_resp = MagicMock()
        api_resp.status_code = 200
        api_resp.json.return_value = {"result": "ok"}
        session_instance.request.return_value = api_resp

        client = FreqtradeClient("http://test", "user", "pass")
        client.access_token = "valid_token"

        res = client._request("GET", "balance")
        assert res == {"result": "ok"}

        session_instance.request.assert_called_with(
            "GET",
            "http://test/api/v1/balance",
            headers={"Authorization": "Bearer valid_token"},
        )


def test_freqtrade_client_relogin_on_401():
    with patch("scripts.sentinel.requests.Session") as MockSession:
        session_instance = MockSession.return_value

        # First request: 401
        resp_401 = MagicMock()
        resp_401.status_code = 401

        # Second request: 200
        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.json.return_value = {"result": "ok"}

        session_instance.request.side_effect = [resp_401, resp_200]

        # Login response
        login_resp = MagicMock()
        login_resp.status_code = 200
        login_resp.json.return_value = {"access_token": "new_token"}
        session_instance.post.return_value = login_resp

        client = FreqtradeClient("http://test", "user", "pass")
        client.access_token = "expired_token"

        res = client._request("GET", "balance")

        # Should have called login
        session_instance.post.assert_called()
        # Should have updated token
        assert client.access_token == "new_token"
        # Should have returned success
        assert res == {"result": "ok"}
