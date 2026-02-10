from unittest.mock import patch

import pytest

from scripts.sentinel import Sentinel


@pytest.fixture
def sentinel_fixture():
    with patch("scripts.sentinel.Sentinel._load_config") as mock_load_config:
        mock_load_config.return_value = {
            "api_server": {
                "enabled": True,
                "listen_ip_address": "127.0.0.1",
                "listen_port": 8080,
                "username": "user",
                "password": "password",
            },
            "stake_currency": "USDT",
            "strategy": "MyStrategy",
        }
        sentinel = Sentinel("config.json", dry_run=True)
        sentinel.auth_token = "mock_token"
        return sentinel


def test_init(sentinel_fixture):
    assert sentinel_fixture.api_url == "http://127.0.0.1:8080/api/v1"
    assert sentinel_fixture.drawdown_threshold == 0.05
    assert sentinel_fixture.btc_drop_threshold == 0.10


def test_get_balance(sentinel_fixture):
    with patch("scripts.sentinel.Sentinel._request") as mock_request:
        mock_request.return_value = {"total": 1000.0}
        balance = sentinel_fixture.get_balance()
        assert balance == 1000.0
        mock_request.assert_called_with("GET", "/balance")


def test_get_balance_fail(sentinel_fixture):
    with patch("scripts.sentinel.Sentinel._request") as mock_request:
        mock_request.side_effect = Exception("API Error")
        balance = sentinel_fixture.get_balance()
        assert balance == 0.0


def test_get_btc_price_candles(sentinel_fixture):
    with patch("scripts.sentinel.Sentinel._request") as mock_request:
        # Success on first try (/pair_candles)
        mock_request.side_effect = [
            {"data": [[0, 0, 0, 0, 50000.0, 0]]},  # candles response
        ]
        price = sentinel_fixture.get_btc_price()
        assert price == 50000.0
        assert mock_request.call_count == 1
        assert "pair_candles" in mock_request.call_args[0][1]


def test_get_btc_price_history(sentinel_fixture):
    with patch("scripts.sentinel.Sentinel._request") as mock_request:
        # Failure on first try, success on second (/pair_history)
        mock_request.side_effect = [
            Exception("Candles failed"),
            {"data": [[0, 0, 0, 0, 48000.0, 0]]},  # history response
        ]
        price = sentinel_fixture.get_btc_price()
        assert price == 48000.0
        assert mock_request.call_count == 2
        assert mock_request.call_args_list[1][0][1] == "/pair_history"


def test_check_drawdown(sentinel_fixture):
    # Initial balance
    assert not sentinel_fixture.check_drawdown(1000.0)

    # Higher balance (new peak)
    assert not sentinel_fixture.check_drawdown(1100.0)

    # Small drop
    assert not sentinel_fixture.check_drawdown(1090.0)

    # Big drop (> 5%)
    # 1100 * 0.95 = 1045
    assert sentinel_fixture.check_drawdown(1000.0)  # 1100 -> 1000 is ~9% drop


def test_check_btc_drop(sentinel_fixture):
    # Initial price
    assert not sentinel_fixture.check_btc_drop(50000.0)

    # Higher price (new peak)
    assert not sentinel_fixture.check_btc_drop(55000.0)

    # Small drop
    assert not sentinel_fixture.check_btc_drop(54000.0)

    # Big drop (> 10%)
    # 55000 * 0.90 = 49500
    assert sentinel_fixture.check_btc_drop(49000.0)  # 55000 -> 49000 is ~11% drop


def test_emergency_actions(sentinel_fixture):
    sentinel_fixture.dry_run = False

    with patch("scripts.sentinel.Sentinel._request") as mock_request:
        sentinel_fixture.emergency_stop()
        mock_request.assert_called_with("POST", "/stop")

    with patch("scripts.sentinel.Sentinel._request") as mock_request:
        sentinel_fixture.emergency_liquidate()
        mock_request.assert_called_with("POST", "/forceexit", data={"tradeid": "all"})


def test_emergency_actions_dry_run(sentinel_fixture):
    sentinel_fixture.dry_run = True

    with patch("scripts.sentinel.Sentinel._request") as mock_request:
        sentinel_fixture.emergency_stop()
        mock_request.assert_not_called()

        sentinel_fixture.emergency_liquidate()
        mock_request.assert_not_called()


def test_send_alert(sentinel_fixture):
    # This is a placeholder, just ensure it doesn't crash
    with patch("logging.Logger.info") as mock_log:
        sentinel_fixture.send_alert("Test Alert")
        mock_log.assert_called()


def test_run_logic(sentinel_fixture):
    # Mock methods to test the main loop logic without infinite loop
    sentinel_fixture.dry_run = True

    # We'll throw an exception to break the while True loop after one iteration
    with patch("time.sleep", side_effect=InterruptedError("Stop Loop")):
        with patch.object(sentinel_fixture, "get_balance", return_value=1000.0):
            with patch.object(sentinel_fixture, "get_btc_price", return_value=50000.0):
                with patch.object(sentinel_fixture, "check_drawdown", return_value=True):
                    with patch.object(sentinel_fixture, "emergency_liquidate") as mock_liq:
                        with patch.object(sentinel_fixture, "emergency_stop") as mock_stop:
                            try:
                                sentinel_fixture.run()
                            except InterruptedError:
                                pass  # Should not be reached because break is called on trigger

                            mock_liq.assert_called_once()
                            mock_stop.assert_called_once()
